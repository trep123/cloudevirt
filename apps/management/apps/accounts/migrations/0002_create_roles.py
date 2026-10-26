"""初始化内置角色分组。

权限绑定由 post_migrate 信号触发的 sync_role_permissions() 完成，
确保权限对象已创建后再绑定。
"""

from django.db import migrations, transaction

from apps.accounts.roles import ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER, sync_role_permissions


def create_roles(apps, schema_editor) -> None:
    """创建三个内置角色分组，并在事务提交后绑定权限。"""
    group_model = apps.get_model('auth', 'Group')
    for role_name in (ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER):
        group_model.objects.get_or_create(name=role_name)
    # 权限对象由 post_migrate 创建，因此等事务提交后再绑定
    transaction.on_commit(sync_role_permissions)


def remove_roles(apps, schema_editor) -> None:
    """删除内置角色分组（仅在回滚迁移时执行）。"""
    group_model = apps.get_model('auth', 'Group')
    group_model.objects.filter(name__in=[ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER]).delete()


class Migration(migrations.Migration):
    """创建内置角色的数据迁移。"""

    dependencies = [
        ('accounts', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [migrations.RunPython(create_roles, remove_roles)]
