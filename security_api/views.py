import json
import uuid
from datetime import datetime
import threading
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET

from security_api.models import PipelineTask
from security_api.tasks import run_pipeline_background_task

@csrf_exempt
@require_POST
def run_pipeline_api(request):
    try:
        payload = json.loads(request.body)
        print(f"========== DEBUG FRONTEND PAYLOAD ==========\n{payload}\n============================================")
        env_config = {
            "ConstellationConfig": int(payload.get("ConstellationConfig")),
            "DegradedEdgeRatio": float(payload.get("DegradedEdgeRatio")),
            "EdgeDisconnectRatio": float(payload.get("EdgeDisconnectRatio")),
            "EdgeBandwidthMeanDecreaseRatio": float(payload.get("EdgeBandwidthMeanDecreaseRatio")),
            "EdgeBandwidthDecreaseStd": float(payload.get("EdgeBandwidthDecreaseStd")),
            "TrafficProfile": str(payload.get("TrafficProfile")),
            "PacketSizeMean": float(payload.get("PacketSizeMean")) * 1e9,
            "PacketSizeStd": float(payload.get("PacketSizeStd")) * 1e9,
        }
        print(f"========== DEBUG ENV CONFIG ==========\n{env_config}\n============================================")
    except Exception as e:
        return JsonResponse({"status": "error", "message": f"参数解析错误: {str(e)}"}, status=400)

    # 用精确到毫秒的时间戳字符串作为 task_id，以兼容落盘时的 start_timestamp 和前端基于字符串和数值的最新批次排序
    task_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    PipelineTask.objects.create(task_id=task_id, status='running', current_stage='Simulation')

    # 发送任务给 Celery Worker
    run_pipeline_background_task.delay(env_config, task_id)

    return JsonResponse({
        "status": "success", 
        "message": "仿真任务已通过 Celery 在后台可靠启动",
        "task_id": task_id,
        "env_config": env_config
    })

@require_GET
def get_task_status_api(request, task_id):
    try:
        task = PipelineTask.objects.get(task_id=task_id)
        return JsonResponse({
            "status": "success",
            "task_id": task.task_id,
            "pipeline_status": task.status,
            "current_stage": task.current_stage,
            "error_message": task.error_message
        })
    except PipelineTask.DoesNotExist:
        return JsonResponse({"status": "error", "message": "任务不存在"}, status=404)


@require_GET
def get_task_results_api(request, task_id):
    try:
        from .models import StepEvaluate, FailureAnalysis, SelfHealing
        stage = request.GET.get('stage', 'iterative')
        
        if stage == 'iterative':
            evals = StepEvaluate.objects.filter(start_timestamp=task_id).select_related('scenario')
            total_cases = evals.count()
            
            data_list = []
            for ev in evals:
                # 重新合并基础指标与场景参数，以维持前端扁平数据结构
                row = {
                    "id": ev.id,
                    "start_timestamp": ev.start_timestamp,
                    "round_index": ev.round_index,
                    "test_id": ev.test_id,
                    "step_index": ev.step_index,
                    "PacketLossRate": ev.PacketLossRate,
                    "NetworkThroughput": ev.NetworkThroughput,
                    "BandwidthUtilization": ev.BandwidthUtilization,
                    "AvgPacketNodeVisits": ev.AvgPacketNodeVisits,
                    "CumulativeReward": ev.CumulativeReward,
                    "AverageInferenceTime": ev.AverageInferenceTime,
                    "AverageE2eDelay": ev.AverageE2eDelay,
                    "AverageHopCount": ev.AverageHopCount,
                    "AverageComputingRatio": ev.AverageComputingRatio,
                    "ComputingWaitingTime": ev.ComputingWaitingTime,
                    "AverageEndingReward": ev.AverageEndingReward,
                    "failure_score_v2": ev.failure_score_v2,
                    "fused_score": ev.fused_score,
                    "timestamp": ev.timestamp,
                }
                if ev.scenario:
                    row.update({
                        "ConstellationConfig": ev.scenario.ConstellationConfig,
                        "DegradedEdgeRatio": ev.scenario.DegradedEdgeRatio,
                        "EdgeDisconnectRatio": ev.scenario.EdgeDisconnectRatio,
                        "EdgeBandwidthMeanDecreaseRatio": ev.scenario.EdgeBandwidthMeanDecreaseRatio,
                        "EdgeBandwidthDecreaseStd": ev.scenario.EdgeBandwidthDecreaseStd,
                        "PoissonRate": ev.scenario.PoissonRate,
                        "MeanIntervalTime": ev.scenario.MeanIntervalTime,
                        "PacketGenerationInterval": ev.scenario.PacketGenerationInterval,
                        "PacketSizeMean": ev.scenario.PacketSizeMean,
                        "PacketSizeStd": ev.scenario.PacketSizeStd,
                        "StateObservationAttack_level": ev.scenario.StateObservationAttack_level,
                        "ActionAttack_level": ev.scenario.ActionAttack_level,
                        "StateTransferAttack_level": ev.scenario.StateTransferAttack_level,
                        "RewardAttack_level": ev.scenario.RewardAttack_level,
                        "ExperiencePoolAttack_level": ev.scenario.ExperiencePoolAttack_level,
                        "ModelTampAttack_level": ev.scenario.ModelTampAttack_level,
                    })
                data_list.append(row)

            return JsonResponse({
                'status': 'success',
                'data': data_list,
                'dashboard_metrics': {
                    'total_test_cases': total_cases,
                }
            })
        elif stage == 'analysis':
            analysis = FailureAnalysis.objects.filter(start_timestamp=task_id).values()
            total_cases = analysis.count()
            return JsonResponse({
                'status': 'success',
                'data': list(analysis),
                'dashboard_metrics': {
                    'total_analysis_cases': total_cases,
                }
            })
        elif stage == 'healing':
            healing = SelfHealing.objects.filter(start_timestamp=task_id).values()
            total_cases = healing.count()
            return JsonResponse({
                'status': 'success',
                'data': list(healing),
                'dashboard_metrics': {
                    'total_healing_cases': total_cases,
                }
            })
        else:
            return JsonResponse({"status": "error", "message": "Unknown stage"}, status=400)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@require_GET
def get_historical_results_api(request):
    try:
        from .models import StepEvaluate, FailureAnalysis, SelfHealing, TestScenarioConfig
        stage = request.GET.get('stage', 'iterative')
        
        if stage == 'iterative':
            evaluations = StepEvaluate.objects.all().values()
            configs = TestScenarioConfig.objects.all().values()
            return JsonResponse({'status': 'success', 'data': {'evaluations': list(evaluations), 'configs': list(configs)}})
        elif stage == 'analysis':
            analysis = FailureAnalysis.objects.all().values()
            return JsonResponse({'status': 'success', 'data': list(analysis)})
        elif stage == 'healing':
            healing = SelfHealing.objects.all().values()
            return JsonResponse({'status': 'success', 'data': list(healing)})
        else:
            return JsonResponse({"status": "error", "message": "Unknown stage"}, status=400)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
