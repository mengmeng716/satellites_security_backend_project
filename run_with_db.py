#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""run_with_db.py: 结合 Django 后端直接运行全流程，并将结果直接插入数据库。"""

import os
import sys

# 1. 挂载当前目录为 Django 项目路径并初始化环境
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "satellites_security_backend.settings")

import django
django.setup()

# 2. 导入刚才配置好的 Django 模型
from security_api.models import StepEvaluate, FailureAnalysis, SelfHealing, PipelineTask, TestScenarioConfig

# 3. 导入核心算法任务的主函数
from algo.run_full_project_pipeline import main

class DjangoDatabaseWriter:
    """满足算法接口约定的写入器类"""
    def __init__(self, task_id=None):
        self.task_id = task_id  # 实例化时记住当前的任务ID

    def update_stage(self, new_stage):
        """提供一个用来更新阶段的方法"""
        if self.task_id:
            PipelineTask.objects.filter(task_id=self.task_id).update(current_stage=new_stage)

    def write_test_scenario_config(self, rows):
        if self.task_id:
            for row in rows:
                row['start_timestamp'] = self.task_id
        instances = [TestScenarioConfig(**row) for row in rows]
        TestScenarioConfig.objects.bulk_create(instances, batch_size=1000)
        return {"status": "success", "count": len(instances)}

    def write_step_evaluate(self, rows):
        if self.task_id:
            for row in rows:
                row['start_timestamp'] = self.task_id
                
        # 建立到 TestScenarioConfig 的外键关联映射
        config_map = {}
        if self.task_id:
            configs = TestScenarioConfig.objects.filter(start_timestamp=self.task_id)
            for c in configs:
                config_map[(c.start_timestamp, c.test_id)] = c.id
                
        for row in rows:
            mapped_id = config_map.get((row['start_timestamp'], row.get('test_id')))
            if mapped_id:
                row['scenario_id'] = mapped_id

        instances = [StepEvaluate(**row) for row in rows]
        StepEvaluate.objects.bulk_create(instances, batch_size=1000)
        return {"status": "success", "count": len(instances)}

    def write_failure_analysis(self, rows):
        if self.task_id:
            for row in rows:
                row['start_timestamp'] = self.task_id
        instances = [FailureAnalysis(**row) for row in rows]
        FailureAnalysis.objects.bulk_create(instances, batch_size=1000)
        return {"status": "success", "count": len(instances)}

    def write_self_healing(self, rows):
        if self.task_id:
            for row in rows:
                row['start_timestamp'] = self.task_id
        instances = [SelfHealing(**row) for row in rows]
        SelfHealing.objects.bulk_create(instances, batch_size=1000)
        return {"status": "success", "count": len(instances)}

if __name__ == "__main__":
    # 实例化数据库写入器
    db_writer = DjangoDatabaseWriter()
    
    # 打印提示信息
    print("[*] 正在启动注入了数据库写入后端的全流程测试...")
    
    # 执行流水线，同时向流水线注入 database_writer
    sys.exit(main(database_writer=db_writer))
