"""节点管理 应用配置。"""

from django.apps import AppConfig


class NodesConfig(AppConfig):
    """节点管理应用的 Django 配置。"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.nodes'
    verbose_name = '节点管理'
