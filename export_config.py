import os
import csv
import django

# 初始化 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'satellites_security_backend.settings')
django.setup()

from security_api.models import TestScenarioConfig

def export_csv(filename):
    queryset = TestScenarioConfig.objects.all()
    if not queryset.exists():
        print("[-] 数据库中没有 TestScenarioConfig 数据可供导出。")
        return
    
    # 获取所有字段名
    fields = [f.name for f in TestScenarioConfig._meta.fields]
    
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(fields)  # 写入表头
        
        count = 0
        for obj in queryset:
            writer.writerow([getattr(obj, field) for field in fields])
            count += 1
            
    print(f"[+] 成功将 {count} 条 TestScenarioConfig 数据导出到 {filename}！")

if __name__ == "__main__":
    export_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'test_scenario_config_exported.csv')
    export_csv(export_path)
