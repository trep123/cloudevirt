"""监控与对账 应用配置。"""

from django.apps import AppConfig


class MonitoringConfig(AppConfig):
    """监控与对账应用的 Django 配置。"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.monitoring'
    verbose_name = '监控与对账'
