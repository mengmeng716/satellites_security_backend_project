from celery import shared_task
from django.db import connection
from security_api.models import PipelineTask
from run_with_db import DjangoDatabaseWriter
from algo.run_full_project_pipeline import main as pipeline_main

@shared_task(bind=True)
def run_pipeline_background_task(self, config, t_id):
    """
    Celery task that runs the 3-day simulation pipeline in the worker.
    """
    print(f"[*] Celery Worker 开始执行流水线，参数: {config}, 任务ID: {t_id}")
    writer = DjangoDatabaseWriter(task_id=t_id)
    lock_name = f"satsec_pipeline_{t_id}"
    lock_acquired = False
    lock_conn_id = None

    def _current_connection_id():
        with connection.cursor() as cursor:
            cursor.execute("SELECT CONNECTION_ID()")
            row = cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def _is_lock_owned_by_current(lock_key: str, expected_conn_id: int | None) -> bool:
        if expected_conn_id is None:
            return False
        with connection.cursor() as cursor:
            cursor.execute("SELECT IS_USED_LOCK(%s)", [lock_key])
            row = cursor.fetchone()
        if not row or row[0] is None:
            return False
        return int(row[0]) == int(expected_conn_id)

    try:
        # 使用 MySQL advisory lock 防止同一 task_id 被重复消费后并发执行。
        with connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 0)", [lock_name])
            lock_row = cursor.fetchone()
        lock_acquired = bool(lock_row and int(lock_row[0]) == 1)
        if lock_acquired:
            lock_conn_id = _current_connection_id()

        if not lock_acquired:
            print(f"[!] Celery Worker 检测到重复任务执行，已跳过: task_id={t_id}")
            return {"status": "duplicate_skipped", "task_id": t_id}

        task = PipelineTask.objects.filter(task_id=t_id).first()
        if not task:
            print(f"[!] Celery Worker 未找到任务记录，跳过执行: task_id={t_id}")
            return {"status": "task_not_found", "task_id": t_id}

        if task and task.status == 'completed':
            # 已完成任务被重复投递时直接跳过，避免误删历史结果。
            print(f"[!] Celery Worker 检测到已完成任务重复投递，跳过执行: task_id={t_id}")
            return {"status": "already_completed", "task_id": t_id}

        previous_status = task.status
        transitioned = PipelineTask.objects.filter(
            task_id=t_id,
            status__in={'queued', 'failed'},
        ).update(
            status='running',
            current_stage='Simulation',
            error_message=None,
        )

        if transitioned == 0:
            latest_status = PipelineTask.objects.filter(task_id=t_id).values_list('status', flat=True).first()
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

        # Actually execute the algorithm pipeline
        pipeline_main(env_config=config, argv=[], database_writer=writer)

        if not _is_lock_owned_by_current(lock_name, lock_conn_id):
            raise RuntimeError(f"Advisory lock lost during task execution: {t_id}")
        
        PipelineTask.objects.filter(task_id=t_id).update(
            status='completed', 
            current_stage='Finished'
        )
        print("[+] Celery Worker 流水线执行并且写入数据库完毕！")
        return {"status": "success", "task_id": t_id}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        PipelineTask.objects.filter(task_id=t_id).update(
            status='failed', 
            error_message=str(e)
        )
        print(f"[-] Celery Worker 流水线执行崩溃: {e}")
        raise
    finally:
        # 正常/异常都尝试释放锁；释放失败不能覆盖主异常。
        if lock_acquired:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", [lock_name])
            except Exception as release_exc:
                print(f"[WARN] release advisory lock failed: {release_exc}")
