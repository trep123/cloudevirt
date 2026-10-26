"""异步任务 应用配置。"""

from django.apps import AppConfig


class TasksConfig(AppConfig):
    """异步任务应用的 Django 配置。"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.tasks'
    verbose_name = '异步任务'
