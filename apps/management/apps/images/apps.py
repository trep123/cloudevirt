"""镜像管理 应用配置。"""

from django.apps import AppConfig


class ImagesConfig(AppConfig):
    """镜像管理应用的 Django 配置。"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.images'
    verbose_name = '镜像管理'
