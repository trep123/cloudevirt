"""节点 API 权限与响应测试。"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.accounts.roles import sync_role_permissions
from apps.audit.models import AuditAction, AuditEvent
from apps.nodes.models import Node, NodeStatus
from apps.nodes.tests.fakes import FakeAgentClient


class NodeApiTests(TestCase):
    """节点接口的认证、权限与状态展示。"""

    def setUp(self) -> None:
        """同步角色权限后创建各角色用户与一个节点。"""
        # 测试库创建时 post_migrate 不会触发，这里显式同步角色矩阵
        sync_role_permissions()
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser(
            username='node-admin', password='Str0ngPassw0rd'
        )
        self.admin.groups.add(Group.objects.get(name='Admin'))

        self.operator = user_model.objects.create_user(
            username='node-operator', password='Str0ngPassw0rd'
        )
        self.operator.groups.add(Group.objects.get(name='Operator'))

        self.viewer = user_model.objects.create_user(
            username='node-viewer', password='Str0ngPassw0rd'
        )
        self.viewer.groups.add(Group.objects.get(name='Viewer'))

        self.node = Node.objects.create(
            name='node-1',
            endpoint='http://127.0.0.1:9100',
            status=NodeStatus.ONLINE,
            cpu_total=16,
        )

    def test_unauthenticated_list_returns_401(self) -> None:
        """未认证访问节点列表应返回 401。"""
        response = self.client.get('/api/v1/nodes')

        self.assertEqual(response.status_code, 401)

    def test_viewer_can_list_nodes(self) -> None:
        """Viewer 可以查看节点，且响应含采样时间与过期标记。"""
        self.client.login(username='node-viewer', password='Str0ngPassw0rd')

        response = self.client.get('/api/v1/nodes')

        self.assertEqual(response.status_code, 200)
        item = response.json()['results'][0]
        self.assertIn('resource_sampled_at', item)
        self.assertIn('resource_is_stale', item)
        self.assertTrue(item['is_schedulable'])

    def test_operator_cannot_register_node(self) -> None:
        """Operator 注册节点应返回 403 并写拒绝审计。"""
        self.client.login(username='node-operator', password='Str0ngPassw0rd')

        response = self.client.post(
            '/api/v1/nodes',
            {'name': 'node-2', 'endpoint': 'http://127.0.0.1:9101'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error']['code'], 'PERMISSION_DENIED')
        self.assertTrue(
            AuditEvent.objects.filter(
                action=AuditAction.PERMISSION_DENIED, actor_id=self.operator.pk
            ).exists()
        )

    def test_admin_registers_node_with_audit(self) -> None:
        """管理员注册节点应成功并写审计。"""
        self.client.login(username='node-admin', password='Str0ngPassw0rd')

        response = self.client.post(
            '/api/v1/nodes',
            {'name': 'node-3', 'endpoint': 'http://127.0.0.1:9102'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        created = Node.objects.get(name='node-3')
        self.assertTrue(
            AuditEvent.objects.filter(
                action=AuditAction.NODE_REGISTER, target_id=str(created.pk)
            ).exists()
        )

    def test_invalid_node_name_is_rejected(self) -> None:
        """非法节点名应返回 400。"""
        self.client.login(username='node-admin', password='Str0ngPassw0rd')

        response = self.client.post(
            '/api/v1/nodes',
            {'name': 'bad name!', 'endpoint': 'http://127.0.0.1:9103'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'VALIDATION_ERROR')

    def test_operator_can_refresh_node(self) -> None:
        """Operator 具有刷新权限，刷新返回最新节点信息。"""
        self.client.login(username='node-operator', password='Str0ngPassw0rd')

        with mock.patch('apps.nodes.views.refresh_node') as refresh:
            refresh.side_effect = lambda node: node
            response = self.client.post(f'/api/v1/nodes/{self.node.pk}/refresh')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(AuditEvent.objects.filter(action=AuditAction.NODE_REFRESH).exists())

    def test_viewer_cannot_refresh_node(self) -> None:
        """Viewer 无刷新权限应返回 403。"""
        self.client.login(username='node-viewer', password='Str0ngPassw0rd')

        response = self.client.post(f'/api/v1/nodes/{self.node.pk}/refresh')

        self.assertEqual(response.status_code, 403)

    def test_offline_node_is_not_schedulable(self) -> None:
        """离线节点在响应中应标记为不可调度。"""
        self.node.status = NodeStatus.OFFLINE
        self.node.save(update_fields=['status'])
        self.client.login(username='node-viewer', password='Str0ngPassw0rd')

        response = self.client.get(f'/api/v1/nodes/{self.node.pk}')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['is_schedulable'])

    def test_refresh_uses_injected_client_in_service(self) -> None:
        """服务层应允许注入客户端，便于测试与后续复用。"""
        node = Node.objects.create(name='node-9', endpoint='http://127.0.0.1:9109')

        from apps.nodes.services import refresh_node

        refresh_node(node, client=FakeAgentClient())

        node.refresh_from_db()
        self.assertEqual(node.status, NodeStatus.ONLINE)
