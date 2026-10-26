"""账户与权限 应用配置。"""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """账户与权限应用的 Django 配置。"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    verbose_name = '账户与权限'
