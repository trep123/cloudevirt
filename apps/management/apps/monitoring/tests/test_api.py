"""监控 API 权限与响应测试。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.accounts.roles import sync_role_permissions
from apps.monitoring.models import Alert, AlertLevel, AlertStatus
from apps.nodes.models import Node, NodeStatus


class MonitoringApiTests(TestCase):
    """概览、告警与对账触发接口。"""

    def setUp(self) -> None:
        """同步角色并创建各角色用户。"""
        sync_role_permissions()
        user_model = get_user_model()
        for username, role in (
            ('mon-viewer', 'Viewer'),
            ('mon-operator', 'Operator'),
            ('mon-admin', 'Admin'),
        ):
            user = user_model.objects.create_user(username=username, password='Str0ngPassw0rd')
            user.groups.add(Group.objects.get(name=role))
        Node.objects.create(
            name='mon-hv', endpoint='http://127.0.0.1:9100', status=NodeStatus.ONLINE
        )

    def test_unauthenticated_returns_401(self) -> None:
        """未认证应返回 401。"""
        self.assertEqual(self.client.get('/api/v1/monitoring/overview').status_code, 401)

    def test_viewer_can_read_overview(self) -> None:
        """Viewer 可读取概览与告警。"""
        Alert.objects.create(
            type='NODE_OFFLINE',
            level=AlertLevel.CRITICAL,
            message='节点离线',
            status=AlertStatus.ACTIVE,
        )
        self.client.login(username='mon-viewer', password='Str0ngPassw0rd')

        overview = self.client.get('/api/v1/monitoring/overview')
        alerts = self.client.get('/api/v1/monitoring/alerts?status=active')

        self.assertEqual(overview.status_code, 200)
        self.assertIn('nodes', overview.json())
        self.assertEqual(len(overview.json()['active_alerts']), 1)
        self.assertEqual(alerts.status_code, 200)
        self.assertEqual(len(alerts.json()['results']), 1)

    def test_operator_cannot_trigger_reconciliation(self) -> None:
        """Operator 无触发对账权限。"""
        self.client.login(username='mon-operator', password='Str0ngPassw0rd')

        response = self.client.post('/api/v1/monitoring/reconciliation/run')

        self.assertEqual(response.status_code, 403)

    def test_admin_can_trigger_reconciliation(self) -> None:
        """Admin 触发对账返回 202 与批次汇总。"""
        self.client.login(username='mon-admin', password='Str0ngPassw0rd')

        response = self.client.post('/api/v1/monitoring/reconciliation/run')

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertIn('summary', body)
        self.assertEqual(body['summary']['nodes'], 1)
        # 节点不可达（未启动 Agent），应计入失败并标记 PARTIAL
        self.assertEqual(body['status'], 'PARTIAL')
        self.assertEqual(body['summary']['failed'], 1)

    def test_reconciliation_history_is_listed(self) -> None:
        """对账历史可查询。"""
        self.client.login(username='mon-admin', password='Str0ngPassw0rd')
        self.client.post('/api/v1/monitoring/reconciliation/run')

        response = self.client.get('/api/v1/monitoring/reconciliation')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)
