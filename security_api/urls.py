from django.urls import path
from . import views

urlpatterns = [
    path('run-pipeline/', views.run_pipeline_api, name='run_pipeline_api'),
    path('run-pipeline/status/<str:task_id>/', views.get_task_status_api, name='get_task_status_api'),
    path('run-pipeline/results/<str:task_id>/', views.get_task_results_api, name='get_task_results_api'),
    path('run-pipeline/history/', views.get_historical_results_api, name='get_historical_results'),
]
