#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""run_with_db.py: 结合 Django 后端直接运行全流程，并将结果直接插入数据库。"""

import os
import sys
import json
import time
from typing import Dict, List, Tuple

# 1. 挂载当前目录为 Django 项目路径并初始化环境
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "satellites_security_backend.settings")

import django
django.setup()

from django.db import close_old_connections
from django.db.utils import InterfaceError, OperationalError
from django.utils import timezone

# 2. 导入刚才配置好的 Django 模型
from security_api.models import StepEvaluate, FailureAnalysis, SelfHealing, PipelineTask, TestScenarioConfig

# 3. 导入核心算法任务的主函数
from algo.run_full_project_pipeline import main

class DjangoDatabaseWriter:
    """满足算法接口约定的写入器类"""
    RETRYABLE_DB_ERROR_CODES = {2006, 2013, 2014, 2045, 2055}

    def __init__(self, task_id=None):
        self.task_id = task_id  # 实例化时记住当前的任务ID

    @classmethod
    def _is_retryable_db_error(cls, exc: Exception) -> bool:
        code = None
        if getattr(exc, "args", None):
            first = exc.args[0]
            if isinstance(first, int):
                code = first
        message = str(exc).lower()
        return bool(
            code in cls.RETRYABLE_DB_ERROR_CODES
            or "server has gone away" in message
            or "lost connection" in message
        )

    def _run_db_with_retry(self, action_name: str, fn, max_retries: int = 3):
        attempt = 0
        while True:
            try:
                close_old_connections()
                return fn()
            except (OperationalError, InterfaceError) as exc:
                attempt += 1
                if attempt > max_retries or not self._is_retryable_db_error(exc):
                    raise
                wait_seconds = min(1.5, 0.25 * attempt)
                print(
                    f"[WARN] {action_name} hit transient DB error (attempt {attempt}/{max_retries}), "
                    f"retrying in {wait_seconds:.2f}s: {exc}"
                )
                close_old_connections()
                time.sleep(wait_seconds)

    def update_stage(self, new_stage):
        """提供一个用来更新阶段的方法"""
        if self.task_id:
            self._run_db_with_retry(
                "update_stage",
                lambda: PipelineTask.objects.filter(task_id=self.task_id).update(
                    current_stage=new_stage,
                    updated_at=timezone.now(),
                ),
            )

    def heartbeat(self):
        """长任务心跳：刷新 updated_at，便于前端实时感知任务仍在执行。"""
        if self.task_id:
            self._run_db_with_retry(
                "task_heartbeat",
                lambda: PipelineTask.objects.filter(task_id=self.task_id).update(
                    updated_at=timezone.now(),
                ),
            )

    def mark_completed(self):
        """统一写入完成状态，避免状态与阶段不同步。"""
        if self.task_id:
            self._run_db_with_retry(
                "mark_completed",
                lambda: PipelineTask.objects.filter(task_id=self.task_id).update(
                    status='completed',
                    current_stage='Finished',
                    error_message=None,
                    updated_at=timezone.now(),
                ),
            )

    def mark_failed(self, error_message):
        """统一写入失败状态，保证前端可读取到最终失败信息。"""
        if self.task_id:
            self._run_db_with_retry(
                "mark_failed",
                lambda: PipelineTask.objects.filter(task_id=self.task_id).update(
                    status='failed',
                    error_message=str(error_message),
                    updated_at=timezone.now(),
                ),
            )

    def reset_task_rows(self):
        """清理同 task_id 的历史残留数据，保证 Celery 重试/重复投递时幂等。"""
        if not self.task_id:
            return
        def _reset():
            StepEvaluate.objects.filter(start_timestamp=self.task_id).delete()
            FailureAnalysis.objects.filter(start_timestamp=self.task_id).delete()
            SelfHealing.objects.filter(start_timestamp=self.task_id).delete()
            TestScenarioConfig.objects.filter(start_timestamp=self.task_id).delete()

        self._run_db_with_retry("reset_task_rows", _reset)

    @staticmethod
    def _dedupe_config_rows(rows: List[Dict]) -> List[Dict]:
        """按 (start_timestamp, test_id) 去重，后出现的记录覆盖先出现的记录。"""
        unique: Dict[Tuple[str, int], Dict] = {}
        for row in rows:
            ts = str(row.get('start_timestamp', ''))
            test_id = int(row.get('test_id', -1))
            unique[(ts, test_id)] = row
        return list(unique.values())

    @staticmethod
    def _dedupe_rows_by_key(rows: List[Dict], key_fields: Tuple[str, ...]) -> List[Dict]:
        """按指定自然键去重，后出现记录覆盖先出现记录。"""
        unique: Dict[Tuple, Dict] = {}
        for row in rows:
            key = tuple(row.get(field) for field in key_fields)
            unique[key] = row
        return list(unique.values())

    @staticmethod
    def _dedupe_exact_rows(rows: List[Dict]) -> List[Dict]:
        """仅去除完全相同的重复行，避免误删合法不同记录。"""
        unique: Dict[str, Dict] = {}
        for row in rows:
            row_key = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
            unique[row_key] = row
        return list(unique.values())

    def write_test_scenario_config(self, rows):
        if self.task_id:
            for row in rows:
                row['start_timestamp'] = self.task_id

        deduped_rows = self._dedupe_config_rows(rows)
        dropped_in_batch = max(0, len(rows) - len(deduped_rows))

        before_count = None
        if self.task_id:
            before_count = self._run_db_with_retry(
                "write_test_scenario_config.before_count",
                lambda: TestScenarioConfig.objects.filter(start_timestamp=self.task_id).count(),
            )

        instances = [TestScenarioConfig(**row) for row in deduped_rows]
        self._run_db_with_retry(
            "write_test_scenario_config.bulk_create",
            lambda: TestScenarioConfig.objects.bulk_create(instances, batch_size=1000, ignore_conflicts=True),
        )

        inserted_count = len(instances)
        ignored_conflicts = 0
        if before_count is not None:
            after_count = self._run_db_with_retry(
                "write_test_scenario_config.after_count",
                lambda: TestScenarioConfig.objects.filter(start_timestamp=self.task_id).count(),
            )
            inserted_count = max(0, after_count - before_count)
            ignored_conflicts = max(0, len(instances) - inserted_count)

        if dropped_in_batch > 0 or ignored_conflicts > 0:
            print(
                f"[WARN] test_scenario_config dedupe/conflict: "
                f"task_id={self.task_id}, input={len(rows)}, deduped={len(deduped_rows)}, "
                f"dropped_in_batch={dropped_in_batch}, ignored_conflicts={ignored_conflicts}"
            )

        return {
            "status": "success",
            "count": inserted_count,
            "deduped_from": len(rows),
            "dropped_in_batch": dropped_in_batch,
            "ignored_conflicts": ignored_conflicts,
        }

    def write_step_evaluate(self, rows):
        if self.task_id:
            for row in rows:
                row['start_timestamp'] = self.task_id

        original_len = len(rows)
        rows = self._dedupe_rows_by_key(
            rows,
            ('start_timestamp', 'round_index', 'test_id', 'step_index'),
        )
        dropped_in_batch = max(0, original_len - len(rows))
                
        # 建立到 TestScenarioConfig 的外键关联映射
        config_map = {}
        if self.task_id:
            configs = self._run_db_with_retry(
                "write_step_evaluate.load_configs",
                lambda: list(TestScenarioConfig.objects.filter(start_timestamp=self.task_id)),
            )
            for c in configs:
                config_map[(c.start_timestamp, c.test_id)] = c.id
                
        for row in rows:
            mapped_id = config_map.get((row['start_timestamp'], row.get('test_id')))
            if mapped_id:
                row['scenario_id'] = mapped_id

        instances = [StepEvaluate(**row) for row in rows]
        self._run_db_with_retry(
            "write_step_evaluate.bulk_create",
            lambda: StepEvaluate.objects.bulk_create(instances, batch_size=1000),
        )
        if dropped_in_batch > 0:
            print(
                f"[WARN] step_evaluate dedupe: task_id={self.task_id}, dropped_in_batch={dropped_in_batch}"
            )
        return {"status": "success", "count": len(instances)}

    def write_failure_analysis(self, rows):
        if self.task_id:
            for row in rows:
                row['start_timestamp'] = self.task_id

        original_len = len(rows)
        rows = self._dedupe_exact_rows(rows)
        dropped_in_batch = max(0, original_len - len(rows))

        instances = [FailureAnalysis(**row) for row in rows]
        self._run_db_with_retry(
            "write_failure_analysis.bulk_create",
            lambda: FailureAnalysis.objects.bulk_create(instances, batch_size=1000),
        )
        if dropped_in_batch > 0:
            print(
                f"[WARN] failure_analysis dedupe: task_id={self.task_id}, dropped_in_batch={dropped_in_batch}"
            )
        return {"status": "success", "count": len(instances)}

    def write_self_healing(self, rows):
        if self.task_id:
            for row in rows:
                row['start_timestamp'] = self.task_id

        original_len = len(rows)
        rows = self._dedupe_exact_rows(rows)
        dropped_in_batch = max(0, original_len - len(rows))

        instances = [SelfHealing(**row) for row in rows]
        self._run_db_with_retry(
            "write_self_healing.bulk_create",
            lambda: SelfHealing.objects.bulk_create(instances, batch_size=1000),
        )
        if dropped_in_batch > 0:
            print(
                f"[WARN] self_healing dedupe: task_id={self.task_id}, dropped_in_batch={dropped_in_batch}"
            )
        return {"status": "success", "count": len(instances)}

if __name__ == "__main__":
    # 实例化数据库写入器
    db_writer = DjangoDatabaseWriter()
    
    # 打印提示信息
    print("[*] 正在启动注入了数据库写入后端的全流程测试...")
    
    # 执行流水线，同时向流水线注入 database_writer
    sys.exit(main(database_writer=db_writer))
