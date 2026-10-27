"""模板 API 测试。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.accounts.roles import sync_role_permissions
from apps.audit.models import AuditAction, AuditEvent
from apps.templates.models import Template


class TemplateApiTests(TestCase):
    """模板的权限、校验与审计。"""

    def setUp(self) -> None:
        """同步角色并创建各角色用户。"""
        sync_role_permissions()
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(username='tpl-admin', password='Str0ngPassw0rd')
        self.admin.groups.add(Group.objects.get(name='Admin'))
        self.viewer = user_model.objects.create_user(
            username='tpl-viewer', password='Str0ngPassw0rd'
        )
        self.viewer.groups.add(Group.objects.get(name='Viewer'))

    def test_unauthenticated_returns_401(self) -> None:
        """未认证应返回 401。"""
        self.assertEqual(self.client.get('/api/v1/templates').status_code, 401)

    def test_viewer_can_list_but_not_create(self) -> None:
        """Viewer 可查看但不能创建。"""
        self.client.login(username='tpl-viewer', password='Str0ngPassw0rd')

        self.assertEqual(self.client.get('/api/v1/templates').status_code, 200)
        response = self.client.post(
            '/api/v1/templates',
            {'name': 'small', 'vcpu': 2, 'memory_mib': 2048, 'disk_gib': 20},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_creates_template_with_audit(self) -> None:
        """Admin 创建模板成功并留痕。"""
        self.client.login(username='tpl-admin', password='Str0ngPassw0rd')

        response = self.client.post(
            '/api/v1/templates',
            {
                'name': 'standard',
                'vcpu': 4,
                'memory_mib': 4096,
                'disk_gib': 40,
                'description': '标准型',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        template = Template.objects.get(name='standard')
        self.assertEqual(template.vcpu, 4)
        self.assertEqual(template.created_by, self.admin)
        self.assertTrue(
            AuditEvent.objects.filter(
                action=AuditAction.TEMPLATE_CREATE, target_id=str(template.pk)
            ).exists()
        )

    def test_duplicate_name_returns_400(self) -> None:
        """重名应返回 400。"""
        Template.objects.create(name='dup', vcpu=1, memory_mib=512, disk_gib=10)
        self.client.login(username='tpl-admin', password='Str0ngPassw0rd')

        response = self.client.post(
            '/api/v1/templates',
            {'name': 'dup', 'vcpu': 1, 'memory_mib': 512, 'disk_gib': 10},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)

    def test_invalid_spec_returns_400(self) -> None:
        """超限规格应返回 400。"""
        self.client.login(username='tpl-admin', password='Str0ngPassw0rd')

        response = self.client.post(
            '/api/v1/templates',
            {'name': 'bad', 'vcpu': 0, 'memory_mib': 512, 'disk_gib': 10},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)

    def test_admin_updates_and_deletes(self) -> None:
        """Admin 可更新与软删除模板。"""
        template = Template.objects.create(
            name='edit-me', vcpu=2, memory_mib=2048, disk_gib=20, created_by=self.admin
        )
        self.client.login(username='tpl-admin', password='Str0ngPassw0rd')

        response = self.client.patch(
            f'/api/v1/templates/{template.pk}',
            {'description': 'updated'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        template.refresh_from_db()
        self.assertEqual(template.description, 'updated')

        delete = self.client.delete(f'/api/v1/templates/{template.pk}')
        self.assertEqual(delete.status_code, 204)
        template.refresh_from_db()
        self.assertTrue(template.is_deleted)
