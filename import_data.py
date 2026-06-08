import os
import csv
import argparse
import django
from django.db import transaction

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


def list_batch_dirs(data_dir):
    if not os.path.isdir(data_dir):
        return []
    dirs = [
        name for name in os.listdir(data_dir)
        if os.path.isdir(os.path.join(data_dir, name))
    ]
    return sorted(dirs)


def resolve_csv_path(batch_dir, preferred_name, legacy_name=None):
    preferred = os.path.join(batch_dir, preferred_name)
    if os.path.exists(preferred):
        return preferred
    if legacy_name:
        legacy = os.path.join(batch_dir, legacy_name)
        if os.path.exists(legacy):
            return legacy
    return None


def collect_start_timestamps(csv_path):
    if not csv_path or not os.path.exists(csv_path):
        return []

    timestamps = set()
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            st = clean_val(row.get('start_timestamp'))
            if st:
                timestamps.add(st)
    return sorted(timestamps)


def import_test_scenario_config(csv_path):
    if not csv_path or not os.path.exists(csv_path):
        print(f"[-] 文件不存在跳过: {csv_path}")
        return []

    print(f"[*] 开始导入 TestScenarioConfig 数据: {csv_path}")
    processed_count = 0
    created_count = 0
    updated_count = 0
    start_timestamps = set()
    model_fields = {f.name for f in TestScenarioConfig._meta.fields}

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            clean_row = {}
            for k, v in row.items():
                if k in model_fields and k != 'id':
                    clean_row[k] = clean_val(v)
            start_timestamp = clean_row.get('start_timestamp')
            test_id = clean_row.get('test_id')
            if not start_timestamp or test_id is None:
                continue

            defaults = dict(clean_row)
            defaults.pop('start_timestamp', None)
            defaults.pop('test_id', None)

            _, created = TestScenarioConfig.objects.update_or_create(
                start_timestamp=start_timestamp,
                test_id=test_id,
                defaults=defaults,
            )
            processed_count += 1
            if created:
                created_count += 1
            else:
                updated_count += 1
            start_timestamps.add(start_timestamp)

    print(
        f"[+] TestScenarioConfig 处理 {processed_count} 条（新建 {created_count} 条，覆盖更新 {updated_count} 条）\n"
    )
    return sorted(start_timestamps)


def import_table_append(model_class, csv_path, boolean_fields=None, overwrite_start_timestamps=None):
    if not csv_path or not os.path.exists(csv_path):
        print(f"[-] 文件不存在跳过: {csv_path}")
        return 0

    print(f"[*] 开始导入 {model_class.__name__} 数据: {csv_path}")
    records = []
    boolean_fields = boolean_fields or []
    overwrite_start_timestamps = overwrite_start_timestamps or []
    model_fields = {f.name for f in model_class._meta.fields}

    if overwrite_start_timestamps:
        deleted_rows, _ = model_class.objects.filter(start_timestamp__in=overwrite_start_timestamps).delete()
        print(f"[=] {model_class.__name__} 已删除批次旧数据 {deleted_rows} 条，准备覆盖导入")

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

    model_class.objects.bulk_create(records, batch_size=1000)
    print(f"[+] 成功插入 {len(records)} 条 {model_class.__name__} 数据\n")
    return len(records)

def import_step_evaluate(csv_path):
    if not csv_path or not os.path.exists(csv_path):
        print(f"[-] 文件不存在跳过: {csv_path}")
        return 0

    print(f"[*] 开始导入 StepEvaluate 数据: {csv_path}")

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
    print(f"[+] 成功插入 {len(final_step_objs)} 条 StepEvaluate 数据\n")
    return len(final_step_objs)


def import_step_evaluate_overwrite(csv_path, overwrite_start_timestamps=None):
    overwrite_start_timestamps = overwrite_start_timestamps or []
    if overwrite_start_timestamps:
        deleted_rows, _ = StepEvaluate.objects.filter(start_timestamp__in=overwrite_start_timestamps).delete()
        print(f"[=] StepEvaluate 已删除批次旧数据 {deleted_rows} 条，准备覆盖导入")
    return import_step_evaluate(csv_path)


def import_one_batch(batch_dir):
    test_scenario_config_csv = resolve_csv_path(batch_dir, 'test_scenario_config_export.csv', 'test_scenario_config.csv')
    step_evaluate_csv = resolve_csv_path(batch_dir, 'step_evaluate_export.csv', 'step_evaluate.csv')
    failure_analysis_csv = resolve_csv_path(batch_dir, 'failure_analysis_export.csv', 'failure_analysis.csv')
    self_healing_csv = resolve_csv_path(batch_dir, 'self_healing_export.csv', 'self_healing.csv')

    with transaction.atomic():
        start_timestamps = import_test_scenario_config(test_scenario_config_csv)

        # 以本批次 start_timestamp 为覆盖粒度，只覆盖同批次旧数据，不影响其它批次
        overwrite_start_timestamps = set(start_timestamps)
        overwrite_start_timestamps.update(collect_start_timestamps(step_evaluate_csv))
        overwrite_start_timestamps.update(collect_start_timestamps(failure_analysis_csv))
        overwrite_start_timestamps.update(collect_start_timestamps(self_healing_csv))
        overwrite_start_timestamps = sorted(overwrite_start_timestamps)

        if overwrite_start_timestamps:
            print(f"[=] 本批次将覆盖 start_timestamp: {', '.join(overwrite_start_timestamps)}")

        import_step_evaluate_overwrite(step_evaluate_csv, overwrite_start_timestamps=overwrite_start_timestamps)
        import_table_append(
            FailureAnalysis,
            failure_analysis_csv,
            overwrite_start_timestamps=overwrite_start_timestamps,
        )
        import_table_append(
            SelfHealing,
            self_healing_csv,
            boolean_fields=['success'],
            overwrite_start_timestamps=overwrite_start_timestamps,
        )


def parse_args():
    parser = argparse.ArgumentParser(description='按批次目录导入安全 Pipeline CSV 数据（重复即覆盖，不删其它批次）')
    parser.add_argument(
        '--data-dir',
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'),
        help='批次目录根路径（默认: 项目根目录/data）',
    )
    parser.add_argument(
        '--batches',
        nargs='*',
        default=None,
        help='指定要导入的批次目录名；不传则导入 data-dir 下全部批次目录',
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()

    if args.batches:
        batch_names = args.batches
    else:
        batch_names = list_batch_dirs(args.data_dir)

    if not batch_names:
        print(f"[-] 未找到可导入批次目录: {args.data_dir}")
        raise SystemExit(1)

    print(f"[*] 将导入 {len(batch_names)} 个批次目录（重复数据按 start_timestamp 覆盖，且不删除其它批次）")
    for name in batch_names:
        batch_dir = os.path.join(args.data_dir, name)
        if not os.path.isdir(batch_dir):
            print(f"[-] 批次目录不存在，跳过: {batch_dir}")
            continue
        print(f"\n========== 导入批次: {name} ==========")
        import_one_batch(batch_dir)

    print("\n所有导入任务执行完毕。")
