import os
import csv
import django

# 初始化 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'satellites_security_backend.settings')
django.setup()

from security_api.models import (
    FailureAnalysis,
    SelfHealing,
    StepEvaluate,
    TestScenarioConfig,
)

def export_single_table(model_cls, output_filename: str):
    """Export a single Django model table to CSV."""
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(BASE_DIR, 'data', output_filename)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    field_names = [f.name for f in model_cls._meta.fields]

    print(f"[*] 开始导出 {model_cls.__name__} 数据...")

    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(field_names)

        records = model_cls.objects.all()
        count = 0

        for record in records:
            row_data = [getattr(record, field) for field in field_names]
            writer.writerow(row_data)
            count += 1

    print(f"[+] {model_cls.__name__}: 成功导出 {count} 条数据到: {output_path}")


def export_tables_to_csv():
    targets = [
        (TestScenarioConfig, 'test_scenario_config_export.csv'),
        (StepEvaluate, 'step_evaluate_export.csv'),
        (FailureAnalysis, 'failure_analysis_export.csv'),
        (SelfHealing, 'self_healing_export.csv'),
    ]
    for model_cls, filename in targets:
        export_single_table(model_cls, filename)

if __name__ == "__main__":
    export_tables_to_csv()