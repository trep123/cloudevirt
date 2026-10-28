"""镜像 API 权限与响应测试。"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.accounts.roles import sync_role_permissions
from apps.audit.models import AuditAction, AuditEvent
from apps.images.models import Image, ImageStatus
from apps.nodes.models import Node, NodeStatus

GOOD_INFO = {
    'format': 'QCOW2',
    'size_bytes': 196640,
    'virtual_size_bytes': 2147483648,
    'checksum_sha256': 'b' * 64,
}


class ImageApiTests(TestCase):
    """镜像接口的权限边界。"""

    def setUp(self) -> None:
        """同步角色、创建用户与节点。"""
        sync_role_permissions()
        user_model = get_user_model()
        self.operator = user_model.objects.create_user(
            username='image-operator', password='Str0ngPassw0rd'
        )
        self.operator.groups.add(Group.objects.get(name='Operator'))
        self.viewer = user_model.objects.create_user(
            username='image-viewer', password='Str0ngPassw0rd'
        )
        self.viewer.groups.add(Group.objects.get(name='Viewer'))
        self.node = Node.objects.create(
            name='api-node', endpoint='http://127.0.0.1:9100', status=NodeStatus.ONLINE
        )

    def test_unauthenticated_returns_401(self) -> None:
        """未认证应返回 401。"""
        self.assertEqual(self.client.get('/api/v1/images').status_code, 401)

    def test_viewer_can_list_images(self) -> None:
        """Viewer 可查看镜像列表。"""
        Image.objects.create(name='existing', status=ImageStatus.READY)
        self.client.login(username='image-viewer', password='Str0ngPassw0rd')

        response = self.client.get('/api/v1/images')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)

    def test_operator_can_import_image(self) -> None:
        """Operator 可导入镜像并写入审计。"""
        self.client.login(username='image-operator', password='Str0ngPassw0rd')

        with mock.patch('apps.nodes.client.AgentClient.inspect_image', return_value=GOOD_INFO):
            response = self.client.post(
                '/api/v1/images',
                {
                    'name': 'ubuntu-24-04',
                    'node': self.node.pk,
                    'relative_path': 'iso/ubuntu.qcow2',
                },
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['image']['status'], 'VERIFYING')
        self.assertTrue(response.json()['task_id'])
        self.assertTrue(AuditEvent.objects.filter(action=AuditAction.IMAGE_IMPORT).exists())

    def test_viewer_cannot_import_image(self) -> None:
        """Viewer 无导入权限应返回 403。"""
        self.client.login(username='image-viewer', password='Str0ngPassw0rd')

        response = self.client.post(
            '/api/v1/images',
            {'name': 'x', 'node': self.node.pk, 'relative_path': 'x.qcow2'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)

    def test_duplicate_name_returns_400(self) -> None:
        """重名镜像应返回 400。"""
        Image.objects.create(name='dup', status=ImageStatus.READY)
        self.client.login(username='image-operator', password='Str0ngPassw0rd')

        with mock.patch('apps.nodes.client.AgentClient.inspect_image', return_value=GOOD_INFO):
            response = self.client.post(
                '/api/v1/images',
                {'name': 'dup', 'node': self.node.pk, 'relative_path': 'dup.qcow2'},
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)

    def test_path_traversal_returns_400(self) -> None:
        """越界路径应返回 400 且不调用 Agent。"""
        self.client.login(username='image-operator', password='Str0ngPassw0rd')

        with mock.patch('apps.nodes.client.AgentClient.inspect_image') as inspect:
            response = self.client.post(
                '/api/v1/images',
                {'name': 'escape', 'node': self.node.pk, 'relative_path': '../etc/passwd'},
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        inspect.assert_not_called()

    def test_operator_can_update_image_metadata(self) -> None:
        """Operator 可更新系统元数据并写审计。"""
        image = Image.objects.create(
            name='meta', status=ImageStatus.READY, relative_path='meta.qcow2'
        )
        self.client.login(username='image-operator', password='Str0ngPassw0rd')

        response = self.client.patch(
            f'/api/v1/images/{image.pk}',
            {'os_family': 'ubuntu', 'os_version': '24.04'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        image.refresh_from_db()
        self.assertEqual(image.os_family, 'ubuntu')
        self.assertEqual(image.os_version, '24.04')
        self.assertTrue(AuditEvent.objects.filter(action=AuditAction.IMAGE_UPDATE).exists())

    def test_viewer_cannot_update_image_metadata(self) -> None:
        """Viewer 无镜像更新权限。"""
        image = Image.objects.create(name='readonly', status=ImageStatus.READY)
        self.client.login(username='image-viewer', password='Str0ngPassw0rd')

        response = self.client.patch(
            f'/api/v1/images/{image.pk}',
            {'os_family': 'debian'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_delete_image(self) -> None:
        """Viewer 无删除权限应返回 403。"""
        image = Image.objects.create(name='keep', status=ImageStatus.READY)
        self.client.login(username='image-viewer', password='Str0ngPassw0rd')

        response = self.client.delete(f'/api/v1/images/{image.pk}')

        self.assertEqual(response.status_code, 403)

    def test_operator_can_delete_image(self) -> None:
        """Operator 可删除镜像并记录审计。"""
        image = Image.objects.create(name='drop', status=ImageStatus.READY, node=self.node)
        self.client.login(username='image-operator', password='Str0ngPassw0rd')

        with mock.patch('apps.nodes.client.AgentClient.delete_image', return_value={}):
            response = self.client.delete(f'/api/v1/images/{image.pk}')

        self.assertEqual(response.status_code, 204)
        image.refresh_from_db()
        self.assertTrue(image.is_deleted)
        self.assertTrue(AuditEvent.objects.filter(action=AuditAction.IMAGE_DELETE).exists())
