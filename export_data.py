import os
import csv
import django

# 初始化 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'satellites_security_backend.settings')
django.setup()

from security_api.models import TestScenarioConfig

def export_table_to_csv():
    # 输出的文件路径
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(BASE_DIR, 'data', 'test_scenario_config_export.csv')
    
    # 确保 data 文件夹存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 获取该模型的所有字段名称
    field_names = [f.name for f in TestScenarioConfig._meta.fields]

    print(f"[*] 开始导出 TestScenarioConfig 数据...")
    
    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        # 1. 写入表头
        writer.writerow(field_names)
        
        # 2. 从数据库读取所有配置记录
        records = TestScenarioConfig.objects.all()
        count = 0
        
        # 3. 逐行写入对应的数据值
        for record in records:
            row_data = [getattr(record, field) for field in field_names]
            writer.writerow(row_data)
            count += 1

    print(f"[+] 成功导出 {count} 条数据到: {output_path}")

if __name__ == "__main__":
    export_table_to_csv()