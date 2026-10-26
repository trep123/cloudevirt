"""网络管理 应用配置。"""

from django.apps import AppConfig


class NetworksConfig(AppConfig):
    """网络管理应用的 Django 配置。"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.networks'
    verbose_name = '网络管理'
