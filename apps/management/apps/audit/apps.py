"""审计 应用配置。"""

from django.apps import AppConfig


class AuditConfig(AppConfig):
    """审计应用的 Django 配置。"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.audit'
    verbose_name = '审计'
