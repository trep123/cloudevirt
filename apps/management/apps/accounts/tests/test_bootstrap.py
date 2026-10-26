"""首个管理员引导命令的部署保护测试。"""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.accounts.models import UserProfile


class BootstrapAdminTests(TestCase):
    """验证引导命令必须显式确认，且不可重复创建。"""

    def test_command_refuses_without_env_flag(self) -> None:
        """未设置部署开关时应拒绝执行。"""
        with self.assertRaises(CommandError):
            call_command('bootstrap_admin', '--username', 'first-admin')

    def test_command_creates_admin_with_flag(self) -> None:
        """设置部署开关后应创建管理员并加入 Admin 组。"""
        with self.settings():
            import os

            os.environ['CLOUDVIRT_BOOTSTRAP_ADMIN'] = 'true'
            try:
                call_command('bootstrap_admin', '--username', 'first-admin')
            finally:
                os.environ.pop('CLOUDVIRT_BOOTSTRAP_ADMIN', None)

        user = get_user_model().objects.get(username='first-admin')
        self.assertTrue(user.is_superuser)
        self.assertIn('Admin', user.groups.values_list('name', flat=True))
        self.assertTrue(UserProfile.objects.get(user=user).must_change_password)

    def test_command_refuses_second_admin(self) -> None:
        """已存在管理员时不得再创建。"""
        get_user_model().objects.create_superuser(
            username='existing-admin', password='Str0ngPassw0rd'
        )
        import os

        os.environ['CLOUDVIRT_BOOTSTRAP_ADMIN'] = 'true'
        try:
            with self.assertRaises(CommandError):
                call_command('bootstrap_admin', '--username', 'second-admin')
        finally:
            os.environ.pop('CLOUDVIRT_BOOTSTRAP_ADMIN', None)
