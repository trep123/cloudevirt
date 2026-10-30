"""权限边界测试：认证、角色、越权与提权字段防护。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.accounts.roles import sync_role_permissions
from apps.audit.models import AuditAction, AuditEvent, AuditResult


class PermissionBoundaryTests(TestCase):
    """验证 401 / 403 边界与审计留痕。"""

    def setUp(self) -> None:
        """创建管理员、Viewer 与普通用户。"""
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser(
            username='root-admin', password='Adm1nStr0ngPass', email='admin@example.com'
        )
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.admin.groups.add(admin_group)
        self.viewer = user_model.objects.create_user(
            username='viewer01', password='V1ewerStr0ngPass'
        )
        viewer_group, _ = Group.objects.get_or_create(name='Viewer')
        self.viewer.groups.add(viewer_group)

    def test_roles_are_created_by_migration(self) -> None:
        """迁移应创建三个内置角色分组。"""
        self.assertTrue(Group.objects.filter(name='Admin').exists())
        self.assertTrue(Group.objects.filter(name='Operator').exists())
        self.assertTrue(Group.objects.filter(name='Viewer').exists())

    def test_sync_binds_permissions_and_reports_missing(self) -> None:
        """同步应给 Admin 绑定全部已登记权限，并报告尚不存在的权限。"""
        report = sync_role_permissions()

        admin_group = Group.objects.get(name='Admin')
        self.assertGreater(admin_group.permissions.count(), 0)
        # 所有业务模型均已落地，报告中不应再有待生效权限
        self.assertEqual(report['Admin'], [])
        self.assertEqual(report['Operator'], [])
        self.assertEqual(report['Viewer'], [])
        self.assertEqual(admin_group.permissions.count(), Permission.objects.count())
        self.assertGreater(
            admin_group.permissions.count(),
            Group.objects.get(name='Viewer').permissions.count(),
        )

    def test_student_has_vm_network_image_and_disk_operations(self) -> None:
        """学员可连接网络及管理数据盘，但不能创建网络。"""
        sync_role_permissions()
        student = get_user_model().objects.create_user(
            username='student01', password='Str0ngPassw0rd'
        )
        student.groups.add(Group.objects.get(name='Operator'))

        for codename in (
            'instances.add_instance',
            'instances.start_instance',
            'instances.shutdown_instance',
            'instances.reboot_instance',
            'instances.force_stop_instance',
            'instances.delete_instance',
            'instances.delete_disk_instance',
            'instances.connect_network_instance',
            'instances.manage_data_disk_instance',
            'images.add_image',
            'images.delete_image',
        ):
            self.assertTrue(student.has_perm(codename), codename)
        self.assertFalse(student.has_perm('nodes.add_node'))
        self.assertFalse(student.has_perm('networks.manage_network'))

    def test_general_user_only_has_vm_operations(self) -> None:
        """一般用户可管理自己的虚拟机、保留磁盘和快照，其余模块无写权限。"""
        sync_role_permissions()
        general = get_user_model().objects.create_user(
            username='general01', password='Str0ngPassw0rd'
        )
        general.groups.add(Group.objects.get(name='Viewer'))

        for codename in (
            'instances.add_instance',
            'instances.start_instance',
            'instances.shutdown_instance',
            'instances.reboot_instance',
            'instances.force_stop_instance',
            'instances.delete_instance',
            'instances.delete_disk_instance',
            'instances.connect_network_instance',
            'instances.manage_data_disk_instance',
            'instances.manage_snapshot_instance',
        ):
            self.assertTrue(general.has_perm(codename), codename)
        for codename in (
            'networks.manage_network',
            'images.add_image',
            'images.delete_image',
            'nodes.add_node',
            'nodes.refresh_node',
            'templates.add_template',
            'tasks.cancel_task',
            'tasks.retry_task',
            'accounts.manage_user',
        ):
            self.assertFalse(general.has_perm(codename), codename)

    def test_unauthenticated_access_returns_401(self) -> None:
        """未认证访问用户列表应返回 401。"""
        response = self.client.get('/api/v1/users')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error']['code'], 'UNAUTHORIZED')

    def test_viewer_cannot_create_user_and_is_audited(self) -> None:
        """Viewer 创建用户应返回 403 并写入被拒审计。"""
        self.client.login(username='viewer01', password='V1ewerStr0ngPass')

        response = self.client.post(
            '/api/v1/users', {'username': 'newbie', 'password': 'Str0ngPassw0rd'}
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error']['code'], 'PERMISSION_DENIED')
        denied = AuditEvent.objects.filter(
            action=AuditAction.PERMISSION_DENIED, result=AuditResult.DENIED
        ).first()
        self.assertIsNotNone(denied)
        self.assertEqual(denied.actor_id, self.viewer.pk)
        self.assertEqual(denied.details['required_permission'], 'accounts.manage_user')

    def test_admin_can_list_users(self) -> None:
        """管理员可以查询用户列表，且返回分页结构。"""
        self.client.login(username='root-admin', password='Adm1nStr0ngPass')

        response = self.client.get('/api/v1/users')

        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.json())

    def test_initial_password_must_be_changed_before_business_access(self) -> None:
        """仍在使用初始口令的用户不得访问业务接口。"""
        user_model = get_user_model()
        admin = user_model.objects.create_superuser(
            username='fresh-admin', password='Str0ngPassw0rd'
        )
        admin.groups.add(Group.objects.get(name='Admin'))
        UserProfile.objects.create(
            user=admin, display_name='fresh-admin', must_change_password=True
        )
        self.client.login(username='fresh-admin', password='Str0ngPassw0rd')

        response = self.client.get('/api/v1/users')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error']['message'], '请先修改初始密码')

        change = self.client.post(
            '/api/v1/auth/change-password',
            {'old_password': 'Str0ngPassw0rd', 'new_password': 'An0therStr0ngPass'},
        )
        self.assertEqual(change.status_code, 200)
        self.assertEqual(self.client.get('/api/v1/users').status_code, 200)

    def test_privilege_escalation_fields_are_rejected(self) -> None:
        """客户端提交的 is_superuser / is_staff 不得生效。"""
        self.client.login(username='root-admin', password='Adm1nStr0ngPass')

        response = self.client.post(
            '/api/v1/users',
            {
                'username': 'sneaky',
                'password': 'Str0ngPassw0rd',
                'is_superuser': True,
                'is_staff': True,
                'roles': ['Viewer'],
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(get_user_model().objects.filter(username='sneaky').exists())
