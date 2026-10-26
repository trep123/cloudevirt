"""同步角色分组与权限绑定（可重复执行）。"""

from django.core.management.base import BaseCommand

from apps.accounts.roles import sync_role_permissions


class Command(BaseCommand):
    """按 roles.py 中的矩阵刷新 Group 与 Permission 绑定。"""

    help = '按角色矩阵同步 Group 与 Permission（可重复执行）'

    def handle(self, *args, **options) -> None:
        """执行同步并输出尚未生效的权限。"""
        report = sync_role_permissions()
        for role, missing in report.items():
            self.stdout.write(self.style.SUCCESS(f'角色已同步: {role}'))
            for codename in missing:
                self.stdout.write(self.style.WARNING(f'  待生效: {codename}'))
