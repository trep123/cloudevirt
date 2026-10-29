"""实例创建任务执行器测试。"""

from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.instances.models import (
    DiskStatus,
    Instance,
    ObservedState,
    ReservationStatus,
    ResourceReservation,
)
from apps.instances.services import create_instance
from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.tasks.models import TaskStatus
from common.errors import AppError, ErrorCode

AGENT_RESULT = {
    'uuid': 'placeholder',
    'name': 'cv-test',
    'state': 'RUNNING',
    'vcpu': 2,
    'memory_mib': 1024,
    'disk_path': '/var/lib/cloudvirt/disks/test.qcow2',
    'disk_virtual_size_bytes': 10737418240,
    'created': True,
}


class InstanceExecutorTests(TestCase):
    """执行器成功与失败路径。"""

    def setUp(self) -> None:
        """创建实例并拿到任务。"""
        self.user = make_user('exec-operator', 'Operator')
        self.node = make_node(name='hv-exec')
        self.image = make_image(name='exec-image', relative_path='iso/exec.qcow2')
        self.instance, self.task = create_instance(
            user=self.user,
            name='vm-exec',
            node=self.node,
            image=self.image,
            vcpu=2,
            memory_mib=1024,
            disk_gib=10,
        )
        capabilities = mock.patch(
            'apps.nodes.client.AgentClient.get_json',
            return_value={'image_clone': True, 'iso_install': True, 'start_control': True},
        )
        capabilities.start()
        self.addCleanup(capabilities.stop)

    def test_success_commits_reservation_and_updates_state(self) -> None:
        """创建成功应更新观测状态、磁盘状态并提交预留。"""
        with mock.patch('apps.nodes.client.AgentClient.create_domain', return_value=AGENT_RESULT):
            call_command('run_worker', '--once')

        self.instance.refresh_from_db()
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.SUCCEEDED)
        self.assertEqual(self.instance.operation_status, 'SUCCEEDED')
        self.assertEqual(self.instance.observed_state, ObservedState.RUNNING)
        self.assertFalse(self.instance.observed_state_is_stale)
        disk = self.instance.disks.first()
        disk.refresh_from_db()
        self.assertEqual(disk.status, DiskStatus.READY)
        self.assertEqual(disk.virtual_size_bytes, 10737418240)
        reservation = ResourceReservation.objects.get(instance=self.instance)
        self.assertEqual(reservation.status, ReservationStatus.COMMITTED)

    def test_unknown_state_maps_to_unknown(self) -> None:
        """Agent 返回未知状态时必须映射 UNKNOWN，不能当作运行中。"""
        result = dict(AGENT_RESULT, state='WEIRD')
        with mock.patch('apps.nodes.client.AgentClient.create_domain', return_value=result):
            call_command('run_worker', '--once')

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.observed_state, ObservedState.UNKNOWN)

    def test_uncertain_creation_retains_reservation_for_reconciliation(self) -> None:
        """已调用创建接口后连接失败，不能假设节点未创建资源。"""
        with mock.patch(
            'apps.nodes.client.AgentClient.create_domain',
            side_effect=AppError(ErrorCode.NODE_OFFLINE, '节点离线'),
        ):
            call_command('run_worker', '--once')

        self.instance.refresh_from_db()
        self.task.refresh_from_db()
        self.assertEqual(self.instance.operation_status, 'FAILED')
        self.assertEqual(self.instance.last_error_code, ErrorCode.NODE_OFFLINE)
        self.assertEqual(self.instance.disks.first().status, DiskStatus.FAILED)
        reservation = ResourceReservation.objects.get(instance=self.instance)
        self.assertEqual(reservation.status, ReservationStatus.HELD)
        # 可恢复错误：任务重新排队等待重试
        self.assertEqual(self.task.status, TaskStatus.PENDING)
        self.assertIsNotNone(self.task.next_retry_at)

    def test_missing_instance_fails_task(self) -> None:
        """实例被删除后任务应明确失败。"""
        Instance.objects.filter(pk=self.instance.pk).delete()

        with mock.patch('apps.nodes.client.AgentClient.create_domain') as create:
            call_command('run_worker', '--once')

        create.assert_not_called()
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.FAILED)
        self.assertEqual(self.task.last_error_code, ErrorCode.NOT_FOUND)

    def test_request_payload_matches_instance(self) -> None:
        """调用 Agent 的参数必须与实例记录一致。"""
        with mock.patch(
            'apps.nodes.client.AgentClient.create_domain', return_value=AGENT_RESULT
        ) as create:
            call_command('run_worker', '--once')

        payload = create.call_args.args[0]
        self.assertEqual(payload['uuid'], str(self.instance.uuid))
        self.assertEqual(payload['vcpu'], 2)
        self.assertEqual(payload['memory_mib'], 1024)
        self.assertEqual(payload['disk_gib'], 10)
        self.assertEqual(payload['name'], self.instance.libvirt_domain_name)
