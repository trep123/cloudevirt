"""按最新角色矩阵同步权限绑定。

角色分组由 0002 创建；本迁移确保既有部署升级时刷新学员与一般用户的权限集合。
"""

from django.db import migrations, transaction

from apps.accounts.roles import sync_role_permissions


def sync_permissions(apps, schema_editor) -> None:
    """事务提交后按 roles.py 的矩阵刷新权限绑定。"""
    transaction.on_commit(sync_role_permissions)


class Migration(migrations.Migration):
    """刷新内置角色权限。"""

    dependencies = [
        ('accounts', '0002_create_roles'),
    ]

    operations = [
        migrations.RunPython(sync_permissions, migrations.RunPython.noop),
    ]
