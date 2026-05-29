import os
import sys
import csv
import django
from datetime import datetime

# 初始化 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'satellites_security_backend.settings')
django.setup()

from security_api.models import TestScenarioConfig, StepEvaluate, FailureAnalysis, SelfHealing

def clean_val(v):
    # 处理空字符，写入数据库的 NULL
    if v is None or str(v).strip() == "":
        return None
    return str(v).strip()

def parse_bool(v):
    if v is None or str(v).strip() == "":
        return None
    return str(v).strip().lower() in ['true', '1', 't', 'yes', 'y']

def import_step_evaluate(csv_path):
    if not os.path.exists(csv_path):
        print(f"[-] 文件不存在跳过: {csv_path}")
        return

    print(f"[*] 开始导入 StepEvaluate 数据...")

    step_records_data = []
    step_fields = {f.name for f in StepEvaluate._meta.fields}

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            step_data = {}
            for k, v in row.items():
                if k in step_fields and k != 'id' and k != 'scenario_id' and k != 'scenario':
                    step_data[k] = clean_val(v)
            # 兼容保留 start_timestamp 和 test_id 用于后续映射
            step_data['_start_timestamp'] = clean_val(row.get('start_timestamp'))
            step_data['_test_id'] = clean_val(row.get('test_id'))
            step_records_data.append(step_data)

    db_configs = TestScenarioConfig.objects.all()
    config_id_map = {(str(c.start_timestamp), str(c.test_id)): c.id for c in db_configs}

    final_step_objs = []
    for step_data in step_records_data:
        t_key = (str(step_data.pop('_start_timestamp', None)), str(step_data.pop('_test_id', None)))
        if t_key in config_id_map:
            step_data['scenario_id'] = config_id_map[t_key]
        final_step_objs.append(StepEvaluate(**step_data))

    StepEvaluate.objects.bulk_create(final_step_objs, batch_size=1000)
    print(f"[+] 成功导入 {len(final_step_objs)} 条 StepEvaluate 数据！\n")

def import_table(model_class, csv_path, boolean_fields=None):
    if not os.path.exists(csv_path):
        print(f"[-] 文件不存在跳过: {csv_path}")
        return

    print(f"[*] 开始导入 {model_class.__name__} 数据...")
    records = []
    boolean_fields = boolean_fields or []
    model_fields = {f.name for f in model_class._meta.fields}
    
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            clean_row = {}
            for k, v in row.items():
                if k in model_fields and k != 'id':
                    val = clean_val(v)
                    if k in boolean_fields:
                        val = parse_bool(val)
                    clean_row[k] = val
            records.append(model_class(**clean_row))

    # 使用 bulk_create 批量插入（每次1000条防止内存爆炸）
    model_class.objects.bulk_create(records, batch_size=1000)
    print(f"[+] 成功导入 {len(records)} 条 {model_class.__name__} 数据！\n")

if __name__ == "__main__":
    # 请根据您存放 CSV 的实际路径进行修改
    # 假设这些文件放在项目根目录下的 data 文件夹里
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    CSV_DIR = os.path.join(BASE_DIR, 'data') # 您可以将4个csv挪到此处
    
    test_scenario_config_csv = os.path.join(CSV_DIR, 'test_scenario_config_export.csv')
    step_evaluate_csv = os.path.join(CSV_DIR, 'step_evaluate.csv')
    failure_analysis_csv = os.path.join(CSV_DIR, 'failure_analysis.csv')
    self_healing_csv = os.path.join(CSV_DIR, 'self_healing.csv')

    # 执行大批量导入前进行表删除（包含新增的配置表）
    StepEvaluate.objects.all().delete()
    TestScenarioConfig.objects.all().delete()
    FailureAnalysis.objects.all().delete()
    SelfHealing.objects.all().delete()

    import_table(TestScenarioConfig, test_scenario_config_csv)
    import_step_evaluate(step_evaluate_csv)
    import_table(FailureAnalysis, failure_analysis_csv)
    import_table(SelfHealing, self_healing_csv, boolean_fields=['success'])
    
    print("所有导入任务执行完毕。")
