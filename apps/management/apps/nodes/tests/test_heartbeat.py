"""节点心跳与离线判定测试。"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditAction, AuditEvent
from apps.nodes.models import Node, NodeStatus
from apps.nodes.services import collect_all_nodes, refresh_node
from apps.nodes.tests.fakes import FakeAgentClient
from common.errors import ErrorCode


def build_node(**kwargs) -> Node:
    """创建测试节点。"""
    defaults = {
        'name': 'node-' + str(Node.objects.count() + 1),
        'endpoint': 'http://127.0.0.1:9100',
        'heartbeat_interval_seconds': 5,
        'offline_after_seconds': 20,
    }
    defaults.update(kwargs)
    return Node.objects.create(**defaults)


class HeartbeatTests(TestCase):
    """心跳采集用例。"""

    def test_successful_collection_updates_snapshot(self) -> None:
        """采集成功应更新采样值、采样时间与在线状态。"""
        node = build_node()

        refresh_node(node, client=FakeAgentClient())

        node.refresh_from_db()
        self.assertEqual(node.status, NodeStatus.ONLINE)
        self.assertEqual(node.cpu_total, 16)
        self.assertEqual(node.memory_available_mib, 16384)
        self.assertEqual(node.storage_total_bytes, 3000)
        self.assertEqual(node.storage_free_bytes, 900)
        self.assertFalse(node.resource_is_stale)
        self.assertIsNotNone(node.resource_sampled_at)
        self.assertIsNotNone(node.last_seen_at)
        self.assertTrue(node.is_schedulable)

    def test_failure_preserves_previous_values(self) -> None:
        """采集失败不得把已有资源字段清零，只标记过期。"""
        node = build_node()
        refresh_node(node, client=FakeAgentClient())
        node.refresh_from_db()
        previous_memory = node.memory_available_mib

        refresh_node(node, client=FakeAgentClient(error=ErrorCode.NODE_OFFLINE))

        node.refresh_from_db()
        self.assertEqual(node.memory_available_mib, previous_memory)
        self.assertTrue(node.resource_is_stale)
        self.assertEqual(node.consecutive_failures, 1)
        self.assertEqual(node.last_error_code, ErrorCode.NODE_OFFLINE)
        self.assertEqual(node.status, NodeStatus.ONLINE)

    def test_offline_after_repeated_failures(self) -> None:
        """连续失败达到阈值后应判定离线并写审计。"""
        node = build_node()
        failing = FakeAgentClient(error=ErrorCode.NODE_OFFLINE)

        for _ in range(4):
            refresh_node(node, client=failing)

        node.refresh_from_db()
        self.assertEqual(node.status, NodeStatus.OFFLINE)
        self.assertFalse(node.is_schedulable)
        self.assertTrue(
            AuditEvent.objects.filter(
                action=AuditAction.NODE_OFFLINE, target_type='node', target_id=str(node.pk)
            ).exists()
        )

    def test_offline_by_last_seen_expiry(self) -> None:
        """心跳静默超过阈值也应判定离线。"""
        node = build_node(status=NodeStatus.ONLINE)
        node.last_seen_at = timezone.now() - timedelta(seconds=60)
        node.save(update_fields=['last_seen_at'])

        changed = node.mark_offline_if_expired()

        self.assertTrue(changed)
        self.assertEqual(node.status, NodeStatus.OFFLINE)

    def test_maintenance_status_is_not_overwritten(self) -> None:
        """维护态不得被自动采集改写。"""
        node = build_node(status=NodeStatus.MAINTENANCE)

        refresh_node(node, client=FakeAgentClient())
        node.refresh_from_db()
        self.assertEqual(node.status, NodeStatus.MAINTENANCE)

        node.consecutive_failures = 10
        node.save(update_fields=['consecutive_failures'])
        self.assertFalse(node.mark_offline_if_expired())
        self.assertEqual(node.status, NodeStatus.MAINTENANCE)

    def test_degraded_when_fields_missing(self) -> None:
        """资源字段缺失时应标记降级而不是在线。"""
        node = build_node()
        partial = FakeAgentClient(resources={'cpu_logical': 8})

        refresh_node(node, client=partial)

        node.refresh_from_db()
        self.assertEqual(node.status, NodeStatus.DEGRADED)
        self.assertTrue(node.is_schedulable)

    def test_collect_all_nodes_summary(self) -> None:
        """批量采集应返回汇总。"""
        build_node(name='alpha')
        build_node(name='beta')

        summary = collect_all_nodes()

        self.assertEqual(summary['total'], 2)
        self.assertEqual(summary['failed'], 2)

    def test_refresh_records_error_for_missing_agent(self) -> None:
        """无法连接 Agent 时应记录稳定错误码且不抛异常（便于批量采集）。"""
        node = build_node(endpoint='http://127.0.0.1:59999')

        refresh_node(node)

        node.refresh_from_db()
        self.assertEqual(node.consecutive_failures, 1)
        self.assertTrue(node.last_error_code)
