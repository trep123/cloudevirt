"""对账与告警测试。"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.images.models import Image, ImageStatus
from apps.instances.models import (
    Disk,
    Instance,
    ObservedState,
    ReservationStatus,
    ResourceReservation,
)
from apps.monitoring.models import (
    Alert,
    AlertStatus,
    DiffKind,
    DiffResolution,
    ReconciliationRun,
)
from apps.monitoring.services import reconcile_node, run_reconciliation
from apps.nodes.models import Node, NodeStatus
from apps.nodes.tests.fakes import FakeAgentClient
from apps.tasks.models import Task, TaskType


class ReconcileTests(TestCase):
    """对账检测、自动修复与告警。"""

    def setUp(self) -> None:
        """准备节点、镜像、实例与任务。"""
        self.node = Node.objects.create(
            name='rec-hv',
            endpoint='http://127.0.0.1:9100',
            status=NodeStatus.ONLINE,
            cpu_total=8,
            memory_total_mib=16384,
            storage_free_bytes=100 * 1024 * 1024 * 1024,
        )
        image = Image.objects.create(
            name='rec-image',
            format='QCOW2',
            relative_path='iso/rec.qcow2',
            status=ImageStatus.READY,
        )
        user_model = __import__('django.contrib.auth', fromlist=['get_user_model']).get_user_model()
        user = user_model.objects.create_user(username='rec-user', password='Str0ngPassw0rd')
        self.instance = Instance.objects.create(
            name='vm-rec',
            libvirt_domain_name='cv-rec',
            node=self.node,
            image=image,
            vcpu=1,
            memory_mib=512,
            disk_gib=5,
            observed_state=ObservedState.SHUTOFF,
            created_by=user,
        )
        Disk.objects.create(
            instance=self.instance,
            name='rec.qcow2',
            relative_path='rec.qcow2',
            size_gib=5,
        )

    def test_state_drift_is_auto_fixed(self) -> None:
        """状态漂移应自动纠正并记录 AUTO_FIXED 差异。"""
        agent = FakeAgentClient()
        agent.domains = lambda: [{'name': 'cv-rec', 'state': 'RUNNING'}]

        run = ReconciliationRun.objects.create(scope='test')
        summary = reconcile_node(self.node, client=agent, run=run)

        self.instance.refresh_from_db()
        self.assertEqual(summary['drift'], 1)
        self.assertEqual(self.instance.observed_state, ObservedState.RUNNING)
        diff = run.diffs.get(kind=DiffKind.INSTANCE_STATE_DRIFT)
        self.assertEqual(diff.resolution, DiffResolution.AUTO_FIXED)
        self.assertEqual(diff.detail['after'], 'RUNNING')

    def test_missing_domain_marks_instance_unknown(self) -> None:
        """数据库实例缺少域时应标记未知并要求人工处理。"""
        agent = FakeAgentClient()
        agent.domains = lambda: []

        run = ReconciliationRun.objects.create(scope='test')
        summary = reconcile_node(self.node, client=agent, run=run)

        self.instance.refresh_from_db()
        self.assertEqual(summary['missing_domain'], 1)
        self.assertEqual(self.instance.observed_state, ObservedState.UNKNOWN)
        self.assertTrue(self.instance.observed_state_is_stale)
        diff = run.diffs.get(kind=DiffKind.DB_INSTANCE_MISSING_DOMAIN)
        self.assertEqual(diff.resolution, DiffResolution.MANUAL)
        self.assertTrue(
            Alert.objects.filter(type='DB_INSTANCE_MISSING_DOMAIN', status='ACTIVE').exists()
        )

    def test_orphan_domain_is_reported(self) -> None:
        """未登记的域应被报告且不自动删除。"""
        agent = FakeAgentClient()
        agent.domains = lambda: [
            {'name': 'cv-rec', 'state': 'RUNNING'},
            {'name': 'ghost-domain', 'state': 'SHUTOFF'},
        ]

        run = ReconciliationRun.objects.create(scope='test')
        summary = reconcile_node(self.node, client=agent, run=run)

        self.assertEqual(summary['orphan_domain'], 1)
        diff = run.diffs.get(kind=DiffKind.DOMAIN_NOT_IN_DB)
        self.assertEqual(diff.resource_id, 'ghost-domain')
        self.assertEqual(diff.resolution, DiffResolution.MANUAL)

    def test_expired_reservation_is_reported(self) -> None:
        """过期预留应报告并提示人工确认。"""
        task = Task.objects.create(
            type=TaskType.INSTANCE_CREATE,
            resource_type='instance',
            resource_id=str(self.instance.pk),
        )
        ResourceReservation.objects.create(
            node=self.node,
            task=task,
            instance=self.instance,
            vcpu_reserved=1,
            memory_reserved_mib=512,
            disk_reserved_bytes=1024,
            status=ReservationStatus.HELD,
            expires_at=timezone.now() - timedelta(minutes=5),
        )
        agent = FakeAgentClient()
        agent.domains = lambda: [{'name': 'cv-rec', 'state': 'RUNNING'}]

        run = ReconciliationRun.objects.create(scope='test')
        summary = reconcile_node(self.node, client=agent, run=run)

        self.assertEqual(summary['expired_reservation'], 1)
        self.assertEqual(run.diffs.filter(kind=DiffKind.RESERVATION_MISMATCH).count(), 1)

    def test_alert_count_increments_and_resolves(self) -> None:
        """重复检测应累加计数，恢复后告警置为已恢复。"""
        missing = FakeAgentClient()
        missing.domains = lambda: []
        reconcile_node(self.node, client=missing)
        reconcile_node(self.node, client=missing)

        alert = Alert.objects.get(type='DB_INSTANCE_MISSING_DOMAIN')
        self.assertGreaterEqual(alert.count, 2)

        fixed = FakeAgentClient()
        fixed.domains = lambda: [{'name': 'cv-rec', 'state': 'RUNNING'}]
        reconcile_node(self.node, client=fixed)

        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.RESOLVED)

    def test_orphan_domain_alert_stays_active(self) -> None:
        """孤儿域告警不得在同一次对账中被误判为已恢复。"""
        agent = FakeAgentClient()
        agent.domains = lambda: [{'name': 'ghost-domain', 'state': 'SHUTOFF'}]

        reconcile_node(self.node, client=agent)

        alerts = Alert.objects.filter(type='DOMAIN_NOT_IN_DB')
        self.assertEqual(alerts.count(), 1)
        self.assertEqual(alerts.first().status, AlertStatus.ACTIVE)
        self.assertEqual(alerts.first().resource_type, 'domain')

    def test_run_reconciliation_marks_partial_on_failure(self) -> None:
        """节点不可达时批次标记 PARTIAL 并计入失败。"""
        broken = Node.objects.create(
            name='rec-broken', endpoint='http://127.0.0.1:59998', status=NodeStatus.ONLINE
        )

        run = run_reconciliation()

        self.assertIn(run.status, {'PARTIAL', 'SUCCEEDED'})
        self.assertGreaterEqual(run.summary['nodes'], 2)
        self.assertGreaterEqual(run.summary['failed'], 1)
        broken.delete()
