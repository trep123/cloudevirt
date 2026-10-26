"""虚拟机实例 应用配置。"""

from django.apps import AppConfig


class InstancesConfig(AppConfig):
    """虚拟机实例应用的 Django 配置。"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.instances'
    verbose_name = '虚拟机实例'
