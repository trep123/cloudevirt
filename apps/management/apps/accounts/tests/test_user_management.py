"""用户管理测试：创建、更新、停用、重置密码与审计。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AuditAction, AuditEvent


class UserManagementTests(TestCase):
    """管理员对用户生命周期的操作。"""

    def setUp(self) -> None:
        """登录管理员并创建一个待管理用户。"""
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser(
            username='root-admin', password='Adm1nStr0ngPass'
        )
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.admin.groups.add(admin_group)
        self.client.login(username='root-admin', password='Adm1nStr0ngPass')

    def test_create_user_assigns_roles_and_profile(self) -> None:
        """创建用户应写入档案、角色与审计。"""
        response = self.client.post(
            '/api/v1/users',
            {
                'username': 'operator01',
                'password': 'Str0ngPassw0rd',
                'display_name': '运维一号',
                'roles': ['Operator'],
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn('Operator', response.json()['roles'])
        created = get_user_model().objects.get(username='operator01')
        self.assertEqual(UserProfile.objects.get(user=created).display_name, '运维一号')
        self.assertIn('Operator', created.groups.values_list('name', flat=True))
        self.assertTrue(
            AuditEvent.objects.filter(
                action=AuditAction.USER_CREATE, target_id=str(created.pk)
            ).exists()
        )

    def test_create_user_rejects_duplicate_username(self) -> None:
        """重复用户名应返回 400。"""
        payload = {'username': 'dup-user', 'password': 'Str0ngPassw0rd'}
        self.client.post('/api/v1/users', payload, content_type='application/json')

        response = self.client.post('/api/v1/users', payload, content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'VALIDATION_ERROR')

    def test_deactivate_user_is_audited(self) -> None:
        """停用用户应记录 USER_DISABLE 审计。"""
        user = get_user_model().objects.create_user(
            username='to-disable', password='Str0ngPassw0rd'
        )

        response = self.client.patch(
            f'/api/v1/users/{user.pk}',
            {'is_active': False},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertTrue(
            AuditEvent.objects.filter(
                action=AuditAction.USER_DISABLE, target_id=str(user.pk)
            ).exists()
        )

    def test_delete_user_deactivates_instead_of_removing(self) -> None:
        """删除语义为停用，保留审计链。"""
        user = get_user_model().objects.create_user(username='to-delete', password='Str0ngPassw0rd')

        response = self.client.delete(f'/api/v1/users/{user.pk}')

        self.assertEqual(response.status_code, 204)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertTrue(get_user_model().objects.filter(pk=user.pk).exists())

    def test_reset_password_returns_temporary_password(self) -> None:
        """重置密码应返回一次性口令并强制改密。"""
        user = get_user_model().objects.create_user(username='to-reset', password='Str0ngPassw0rd')

        response = self.client.post(f'/api/v1/users/{user.pk}/reset-password')

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['password'])
        self.assertTrue(UserProfile.objects.get(user=user).must_change_password)
        self.assertTrue(
            AuditEvent.objects.filter(
                action=AuditAction.USER_PASSWORD_RESET, target_id=str(user.pk)
            ).exists()
        )

    def test_reset_password_for_missing_user_returns_404(self) -> None:
        """重置不存在用户的密码应返回 404。"""
        response = self.client.post('/api/v1/users/999999/reset-password')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error']['code'], 'NOT_FOUND')
