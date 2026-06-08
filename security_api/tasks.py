from celery import shared_task
import time
import threading
from typing import Any

import MySQLdb
from django.db import connection
from django.db import close_old_connections
from django.db.utils import InterfaceError, OperationalError
from django.conf import settings
from security_api.models import PipelineTask
from run_with_db import DjangoDatabaseWriter
from algo.run_full_project_pipeline import main as pipeline_main


RETRYABLE_DB_ERROR_CODES = {2006, 2013, 2014, 2045, 2055}


def _is_retryable_db_error(exc: Exception) -> bool:
    code = None
    if getattr(exc, "args", None):
        first = exc.args[0]
        if isinstance(first, int):
            code = first
    message = str(exc).lower()
    return bool(
        code in RETRYABLE_DB_ERROR_CODES
        or "server has gone away" in message
        or "lost connection" in message
    )


def _db_retry(action_name: str, fn, max_retries: int = 3):
    attempt = 0
    while True:
        try:
            close_old_connections()
            return fn()
        except (OperationalError, InterfaceError) as exc:
            attempt += 1
            if attempt > max_retries or not _is_retryable_db_error(exc):
                raise
            wait_seconds = min(1.5, 0.25 * attempt)
            print(
                f"[WARN] {action_name} hit transient DB error (attempt {attempt}/{max_retries}), "
                f"retrying in {wait_seconds:.2f}s: {exc}"
            )
            close_old_connections()
            time.sleep(wait_seconds)


def _build_mysql_connect_kwargs() -> dict[str, Any]:
    db_cfg = settings.DATABASES.get("default", {})
    engine = str(db_cfg.get("ENGINE", ""))
    if "mysql" not in engine:
        raise RuntimeError(f"Unsupported DB engine for advisory lock heartbeat: {engine}")

    kwargs: dict[str, Any] = {
        "host": db_cfg.get("HOST") or "127.0.0.1",
        "user": db_cfg.get("USER") or "",
        "passwd": db_cfg.get("PASSWORD") or "",
        "db": db_cfg.get("NAME") or "",
        "charset": "utf8mb4",
        "autocommit": True,
        "connect_timeout": 10,
        "read_timeout": 10,
        "write_timeout": 10,
    }
    if db_cfg.get("PORT"):
        kwargs["port"] = int(db_cfg["PORT"])

    options = db_cfg.get("OPTIONS", {}) or {}
    if "ssl" in options and options["ssl"]:
        kwargs["ssl"] = options["ssl"]
    return kwargs


class AdvisoryLockKeeper:
    """Owns a dedicated DB connection for advisory lock and periodic keepalive."""

    def __init__(self, lock_name: str, heartbeat_seconds: int = 120):
        self.lock_name = lock_name
        self.heartbeat_seconds = max(10, int(heartbeat_seconds))
        self._conn = None
        self._conn_id: int | None = None
        self._stop_event = threading.Event()
        self._lock_lost_event = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._last_error: str | None = None

    @property
    def connection_id(self) -> int | None:
        return self._conn_id

    @property
    def lock_lost(self) -> bool:
        return self._lock_lost_event.is_set()

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def acquire(self) -> bool:
        self._conn = MySQLdb.connect(**_build_mysql_connect_kwargs())
        with self._conn.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 0)", [self.lock_name])
            row = cursor.fetchone()
            got_lock = bool(row and int(row[0]) == 1)
            if not got_lock:
                return False
            cursor.execute("SELECT CONNECTION_ID()")
            conn_row = cursor.fetchone()
            self._conn_id = int(conn_row[0]) if conn_row and conn_row[0] is not None else None
            # Raise timeout thresholds for this dedicated lock connection.
            cursor.execute("SET SESSION wait_timeout = %s", [28800])
            cursor.execute("SET SESSION interactive_timeout = %s", [28800])

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"advisory-lock-heartbeat-{self.lock_name}",
            daemon=True,
        )
        self._heartbeat_thread.start()
        print(
            f"[*] Advisory lock acquired: {self.lock_name}, conn_id={self._conn_id}, "
            f"heartbeat={self.heartbeat_seconds}s"
        )
        return True

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(self.heartbeat_seconds):
            if self._conn is None:
                self._lock_lost_event.set()
                self._last_error = "heartbeat connection is not initialized"
                return
            try:
                with self._conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    cursor.execute("SELECT IS_USED_LOCK(%s)", [self.lock_name])
                    row = cursor.fetchone()
                if not row or row[0] is None:
                    self._lock_lost_event.set()
                    self._last_error = "advisory lock released unexpectedly"
                    return
                if self._conn_id is not None and int(row[0]) != int(self._conn_id):
                    self._lock_lost_event.set()
                    self._last_error = (
                        f"advisory lock owner changed: expected={self._conn_id}, actual={int(row[0])}"
                    )
                    return
            except Exception as exc:
                self._lock_lost_event.set()
                self._last_error = f"heartbeat failed: {exc}"
                return

    def release(self) -> None:
        self._stop_event.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=2.0)
        if self._conn is None:
            return
        try:
            with self._conn.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", [self.lock_name])
        except Exception as exc:
            print(f"[WARN] release advisory lock failed: {exc}")
        finally:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

@shared_task(bind=True)
def run_pipeline_background_task(self, config, t_id):
    """
    Celery task that runs the 3-day simulation pipeline in the worker.
    """
    print(f"[*] Celery Worker 开始执行流水线，参数: {config}, 任务ID: {t_id}")
    writer = DjangoDatabaseWriter(task_id=t_id)
    lock_name = f"satsec_pipeline_{t_id}"
    heartbeat_seconds = int(getattr(settings, "SATSEC_DB_HEARTBEAT_SECONDS", 120))
    lock_keeper = AdvisoryLockKeeper(lock_name=lock_name, heartbeat_seconds=heartbeat_seconds)
    task_heartbeat_seconds = int(getattr(settings, "SATSEC_TASK_HEARTBEAT_SECONDS", 30))
    task_heartbeat_stop = threading.Event()
    task_heartbeat_thread: threading.Thread | None = None

    def _task_heartbeat_loop() -> None:
        while not task_heartbeat_stop.wait(task_heartbeat_seconds):
            try:
                writer.heartbeat()
            except Exception as exc:
                print(f"[WARN] task heartbeat update failed: {exc}")

    try:
        # 使用 MySQL advisory lock 防止同一 task_id 被重复消费后并发执行。
        lock_acquired = lock_keeper.acquire()

        if not lock_acquired:
            print(f"[!] Celery Worker 检测到重复任务执行，已跳过: task_id={t_id}")
            return {"status": "duplicate_skipped", "task_id": t_id}

        task = _db_retry(
            "task.fetch",
            lambda: PipelineTask.objects.filter(task_id=t_id).first(),
        )
        if not task:
            print(f"[!] Celery Worker 未找到任务记录，跳过执行: task_id={t_id}")
            return {"status": "task_not_found", "task_id": t_id}

        if task and task.status == 'completed':
            # 已完成任务被重复投递时直接跳过，避免误删历史结果。
            print(f"[!] Celery Worker 检测到已完成任务重复投递，跳过执行: task_id={t_id}")
            return {"status": "already_completed", "task_id": t_id}

        previous_status = task.status
        transitioned = _db_retry(
            "task.transition_to_running",
            lambda: PipelineTask.objects.filter(
                task_id=t_id,
                status__in={'queued', 'failed'},
            ).update(
                status='running',
                current_stage='Simulation',
                error_message=None,
            ),
        )

        if transitioned == 0:
            latest_status = _db_retry(
                "task.fetch_latest_status",
                lambda: PipelineTask.objects.filter(task_id=t_id).values_list('status', flat=True).first(),
            )
            if latest_status == 'running':
                print(f"[!] Celery Worker 检测到任务已在运行中，跳过重复执行: task_id={t_id}")
                return {"status": "already_running", "task_id": t_id}
            if latest_status == 'completed':
                print(f"[!] Celery Worker 检测到任务已完成，跳过重复执行: task_id={t_id}")
                return {"status": "already_completed", "task_id": t_id}
            print(f"[!] Celery Worker 任务状态非法，跳过执行: task_id={t_id}, status={latest_status}")
            return {"status": "invalid_status", "task_id": t_id, "pipeline_status": latest_status}

        # 仅在恢复执行场景清理残留：failed/stale running。
        if previous_status == 'failed':
            writer.reset_task_rows()

        task_heartbeat_thread = threading.Thread(
            target=_task_heartbeat_loop,
            name=f"task-heartbeat-{t_id}",
            daemon=True,
        )
        task_heartbeat_thread.start()

        # Actually execute the algorithm pipeline
        pipeline_main(env_config=config, argv=[], database_writer=writer)

        if lock_keeper.lock_lost:
            detail = lock_keeper.last_error or "unknown"
            raise RuntimeError(f"Advisory lock lost during task execution: {t_id}; detail={detail}")
        
        writer.mark_completed()
        print("[+] Celery Worker 流水线执行并且写入数据库完毕！")
        return {"status": "success", "task_id": t_id}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            writer.mark_failed(e)
        except Exception as update_exc:
            print(f"[WARN] failed to update PipelineTask status=failed: {update_exc}")
        print(f"[-] Celery Worker 流水线执行崩溃: {e}")
        raise
    finally:
        task_heartbeat_stop.set()
        if task_heartbeat_thread is not None:
            task_heartbeat_thread.join(timeout=2.0)
        # 正常/异常都尝试释放锁；释放失败不能覆盖主异常。
        lock_keeper.release()
