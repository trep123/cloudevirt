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
        # 终态创建失败会触发回滚删除；测试节点 endpoint 指向真实 Agent，
        # 这里统一拦截删除调用，避免用例对宿主机发出破坏性请求。
        for method, result in (
            ('delete_domain_disks', {'result': 'deleted', 'disk_removed': True}),
            ('delete_domain', {'result': 'deleted', 'disk_removed': False}),
        ):
            patcher = mock.patch(
                f'apps.nodes.client.AgentClient.{method}', return_value=result
            )
            patcher.start()
            self.addCleanup(patcher.stop)

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

    def test_terminal_start_failure_rolls_back_and_releases(self) -> None:
        """创建到达节点但启动校验终态失败：回滚残留域与磁盘并释放预留。"""
        result = dict(AGENT_RESULT, state='SHUTOFF')
        with mock.patch(
            'apps.nodes.client.AgentClient.create_domain', return_value=result
        ), mock.patch(
            'apps.nodes.client.AgentClient.delete_domain_disks',
            return_value={'result': 'deleted', 'disk_removed': True},
        ) as delete_disks:
            call_command('run_worker', '--once')

        self.instance.refresh_from_db()
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.FAILED)
        self.assertEqual(self.instance.operation_status, 'FAILED')
        delete_disks.assert_called_once()
        purged = delete_disks.call_args.args[1]
        disk = self.instance.disks.first()
        self.assertEqual(purged, [disk.relative_path])
        disk.refresh_from_db()
        self.assertEqual(disk.status, DiskStatus.DELETED)
        reservation = ResourceReservation.objects.get(instance=self.instance)
        self.assertEqual(reservation.status, ReservationStatus.RELEASED)

    def test_rollback_preserves_existing_system_disk(self) -> None:
        """直接挂载既有系统盘时，回滚只解除域定义，不删除用户磁盘。"""
        from apps.instances.executors import _rollback_failed_creation

        self.instance.creation_config = {
            'existing_system_file': 'vms/pre.qcow2',
            'clone_mode': 'direct',
        }
        self.instance.save(update_fields=['creation_config'])
        disk = self.instance.disks.first()
        disk.relative_path = 'vms/pre.qcow2'
        disk.save(update_fields=['relative_path'])

        with mock.patch(
            'apps.nodes.client.AgentClient.delete_domain',
            return_value={'result': 'deleted', 'disk_removed': False},
        ) as delete_domain, mock.patch(
            'apps.nodes.client.AgentClient.delete_domain_disks'
        ) as delete_disks:
            rolled_back = _rollback_failed_creation(self.instance, self.task)

        self.assertTrue(rolled_back)
        delete_disks.assert_not_called()
        delete_domain.assert_called_once()
        disk.refresh_from_db()
        self.assertEqual(disk.status, DiskStatus.READY)

    def test_rollback_failure_retains_reservation(self) -> None:
        """回滚调用失败时不能假设资源已清理，保留预留待人工核对。"""
        from apps.instances.executors import _rollback_failed_creation

        with mock.patch(
            'apps.nodes.client.AgentClient.delete_domain_disks',
            side_effect=AppError(ErrorCode.NODE_OFFLINE, '节点离线'),
        ):
            rolled_back = _rollback_failed_creation(self.instance, self.task)

        self.assertFalse(rolled_back)
        reservation = ResourceReservation.objects.get(instance=self.instance)
        self.assertEqual(reservation.status, ReservationStatus.HELD)
