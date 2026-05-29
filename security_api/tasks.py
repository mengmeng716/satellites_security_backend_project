from celery import shared_task
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
    try:
        # Actually execute the algorithm pipeline
        pipeline_main(env_config=config, argv=[], database_writer=writer)
        
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
        raise e
