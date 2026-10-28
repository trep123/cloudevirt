"""实例生命周期操作测试。"""

from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.instances.models import (
    DiskStatus,
    ObservedState,
    ReservationStatus,
    ResourceReservation,
)
from apps.instances.services import create_instance
from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.tasks.models import Task, TaskStatus, TaskType
from common.errors import AppError, ErrorCode


def prepare_instance(username: str = 'life-operator'):
    """创建用户、节点、镜像与实例。"""
    user = make_user(username, 'Operator')
    node = make_node(name=f'hv-{username}')
    image = make_image(name=f'img-{username}', relative_path=f'iso/{username}.qcow2')
    instance, task = create_instance(
        user=user,
        name=f'vm-{username}',
        node=node,
        image=image,
        vcpu=1,
        memory_mib=512,
        disk_gib=5,
    )
    return user, instance, task


class LifecycleExecutorTests(TestCase):
    """执行器对各动作的处理。"""

    def setUp(self) -> None:
        """准备实例并把创建任务标记完成。"""
        self.user, self.instance, self.create_task = prepare_instance()
        Task.objects.filter(pk=self.create_task.pk).update(status=TaskStatus.SUCCEEDED)
        self.instance.operation_status = 'SUCCEEDED'
        self.instance.save(update_fields=['operation_status'])

    def _run(self, action_task_type, agent_return):
        """入队动作任务并执行一轮 worker。"""
        from apps.tasks.services import enqueue

        task = enqueue(
            task_type=action_task_type,
            resource_type='instance',
            resource_id=str(self.instance.pk),
            payload={'action': 'x'},
        )
        with mock.patch('apps.nodes.client.AgentClient.domain_action', return_value=agent_return):
            call_command('run_worker', '--once')
        task.refresh_from_db()
        self.instance.refresh_from_db()
        return task

    def test_start_sets_running(self) -> None:
        """启动成功后观测状态为 RUNNING。"""
        task = self._run(TaskType.INSTANCE_START, {'state': 'RUNNING'})

        self.assertEqual(task.status, TaskStatus.SUCCEEDED)
        self.assertEqual(self.instance.observed_state, ObservedState.RUNNING)
        self.assertEqual(self.instance.operation_status, 'SUCCEEDED')

    def test_shutdown_sets_shutoff(self) -> None:
        """关机成功后观测状态为 SHUTOFF。"""
        task = self._run(TaskType.INSTANCE_SHUTDOWN, {'state': 'SHUTOFF'})

        self.assertEqual(task.status, TaskStatus.SUCCEEDED)
        self.assertEqual(self.instance.observed_state, ObservedState.SHUTOFF)

    def test_force_stop_sets_shutoff(self) -> None:
        """强停成功后观测状态为 SHUTOFF。"""
        task = self._run(TaskType.INSTANCE_FORCE_STOP, {'state': 'SHUTOFF'})

        self.assertEqual(task.status, TaskStatus.SUCCEEDED)
        self.assertEqual(self.instance.observed_state, ObservedState.SHUTOFF)

    @override_settings(INSTANCE_SHUTDOWN_TIMEOUT_SECONDS=0)
    def test_shutdown_timeout_fails_without_force_stop(self) -> None:
        """关机超时应失败并提示可强停，不自动强停。"""
        task = self._run(TaskType.INSTANCE_SHUTDOWN, {'state': 'RUNNING'})

        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertIn('关机超时', task.last_error_message)
        self.assertEqual(self.instance.operation_status, 'FAILED')

    def test_agent_failure_marks_instance_failed(self) -> None:
        """Agent 报错应记录到实例。"""
        from apps.tasks.services import enqueue

        task = enqueue(
            task_type=TaskType.INSTANCE_START,
            resource_type='instance',
            resource_id=str(self.instance.pk),
            payload={'action': 'start'},
        )
        with mock.patch(
            'apps.nodes.client.AgentClient.domain_action',
            side_effect=AppError(ErrorCode.LIBVIRT_UNAVAILABLE, 'libvirt 不可用'),
        ):
            call_command('run_worker', '--once')

        task.refresh_from_db()
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.operation_status, 'FAILED')
        self.assertEqual(self.instance.last_error_code, ErrorCode.LIBVIRT_UNAVAILABLE)
        self.assertEqual(task.status, TaskStatus.PENDING)

    def test_delete_purges_disk_and_releases_reservation(self) -> None:
        """删除成功应软删除实例、标记磁盘已删除并释放预留。"""
        from apps.tasks.services import enqueue

        disk = self.instance.disks.first()
        task = enqueue(
            task_type=TaskType.INSTANCE_DELETE,
            resource_type='instance',
            resource_id=str(self.instance.pk),
            payload={
                'domain_name': self.instance.libvirt_domain_name,
                'purge_disk': True,
                'disk_relative_path': disk.relative_path,
            },
        )

        with mock.patch(
            'apps.nodes.client.AgentClient.delete_domain',
            return_value={'result': 'deleted', 'disk_removed': True},
        ) as delete_call:
            call_command('run_worker', '--once')

        task.refresh_from_db()
        self.instance.refresh_from_db()
        disk.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.SUCCEEDED)
        self.assertTrue(self.instance.is_deleted)
        self.assertTrue(self.instance.disks_deleted)
        self.assertEqual(disk.status, DiskStatus.DELETED)
        self.assertEqual(
            ResourceReservation.objects.get(instance=self.instance).status,
            ReservationStatus.RELEASED,
        )
        delete_call.assert_called_once_with(self.instance.libvirt_domain_name, disk.relative_path)

    def test_delete_keeps_disk_when_not_requested(self) -> None:
        """未选择删除磁盘时不应传递磁盘路径。"""
        from apps.tasks.services import enqueue

        task = enqueue(
            task_type=TaskType.INSTANCE_DELETE,
            resource_type='instance',
            resource_id=str(self.instance.pk),
            payload={'domain_name': self.instance.libvirt_domain_name, 'purge_disk': False},
        )

        with mock.patch(
            'apps.nodes.client.AgentClient.delete_domain',
            return_value={'result': 'deleted', 'disk_removed': False},
        ) as delete_call:
            call_command('run_worker', '--once')

        task.refresh_from_db()
        self.instance.refresh_from_db()
        self.assertTrue(self.instance.is_deleted)
        self.assertFalse(self.instance.disks_deleted)
        delete_call.assert_called_once_with(self.instance.libvirt_domain_name, '')


class LifecycleApiTests(TestCase):
    """生命周期接口的权限与状态分支。"""

    def setUp(self) -> None:
        """准备实例与各角色用户。"""
        self.operator, self.instance, self.create_task = prepare_instance('api-life')
        Task.objects.filter(pk=self.create_task.pk).update(status=TaskStatus.SUCCEEDED)
        self.instance.operation_status = 'SUCCEEDED'
        self.instance.observed_state = ObservedState.SHUTOFF
        self.instance.save(update_fields=['operation_status', 'observed_state'])
        self.viewer = make_user('life-viewer', 'Viewer')
        self.admin = make_user('life-admin', 'Admin')

    def test_start_creates_task(self) -> None:
        """关机状态启动应返回 202 与任务。"""
        self.client.login(username='api-life', password='Str0ngPassw0rd')

        response = self.client.post(f'/api/v1/instances/{self.instance.pk}/start')

        self.assertEqual(response.status_code, 202)
        self.assertIn('task', response.json())
        self.assertTrue(Task.objects.filter(type=TaskType.INSTANCE_START).exists())

    def test_start_when_running_is_idempotent(self) -> None:
        """已运行时启动应返回 200 且不创建任务。"""
        self.instance.observed_state = ObservedState.RUNNING
        self.instance.save(update_fields=['observed_state'])
        self.client.login(username='api-life', password='Str0ngPassw0rd')

        response = self.client.post(f'/api/v1/instances/{self.instance.pk}/start')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['idempotent'])
        self.assertFalse(Task.objects.filter(type=TaskType.INSTANCE_START).exists())

    def test_shutdown_when_shutoff_returns_409(self) -> None:
        """已关机时关机应返回 409。"""
        self.client.login(username='api-life', password='Str0ngPassw0rd')

        response = self.client.post(f'/api/v1/instances/{self.instance.pk}/shutdown')

        self.assertEqual(response.status_code, 409)

    def test_general_user_can_start(self) -> None:
        """一般用户可以启动自己的实例，不能操作他人实例。"""
        self.client.login(username='life-viewer', password='Str0ngPassw0rd')
        foreign = self.client.post(f'/api/v1/instances/{self.instance.pk}/start')
        self.assertEqual(foreign.status_code, 404)
        from django.contrib.auth import get_user_model

        self.instance.created_by = get_user_model().objects.get(username='life-viewer')
        self.instance.save(update_fields=['created_by'])

        response = self.client.post(f'/api/v1/instances/{self.instance.pk}/start')

        self.assertEqual(response.status_code, 202)
        self.assertTrue(Task.objects.filter(type=TaskType.INSTANCE_START).exists())

    def test_stale_operation_status_without_active_task_does_not_block(self) -> None:
        """没有真实活跃任务时，残留的 operation_status 不应阻塞操作。"""
        self.instance.operation_status = 'PENDING'
        self.instance.save(update_fields=['operation_status'])
        self.client.login(username='api-life', password='Str0ngPassw0rd')

        response = self.client.post(f'/api/v1/instances/{self.instance.pk}/start')

        self.assertEqual(response.status_code, 202)

    def test_cancel_pending_action_clears_operation_status(self) -> None:
        """取消等待中的任务应同步清除实例的进行中状态。"""
        self.client.login(username='api-life', password='Str0ngPassw0rd')
        self.client.post(f'/api/v1/instances/{self.instance.pk}/start')
        task = Task.objects.get(type=TaskType.INSTANCE_START)

        response = self.client.post(f'/api/v1/tasks/{task.pk}/cancel')

        self.assertEqual(response.status_code, 200)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.operation_status, 'CANCELLED')
        self.assertIsNone(self.instance.current_task)

    @mock.patch(
        'apps.instances.views.AgentClient.domain_addresses',
        return_value={
            'addresses': [
                {'interface': 'vnet0', 'protocol': 'ipv4', 'address': '192.168.122.10'},
                {'interface': 'vnet0', 'protocol': 'ipv6', 'address': 'fd00::10'},
            ],
            'fetched_at': '2026-10-27T12:00:00Z',
        },
    )
    def test_instance_addresses_returns_ipv4_and_ipv6(self, addresses) -> None:
        """实例地址接口返回 Agent 采集的 IPv4/IPv6。"""
        self.client.login(username='api-life', password='Str0ngPassw0rd')

        response = self.client.get(f'/api/v1/instances/{self.instance.pk}/addresses')

        self.assertEqual(response.status_code, 200)
        protocols = [item['protocol'] for item in response.json()['addresses']]
        self.assertIn('ipv4', protocols)
        self.assertIn('ipv6', protocols)
        addresses.assert_called_once_with(self.instance.libvirt_domain_name)

    @mock.patch(
        'apps.instances.views.AgentClient.domain_interfaces',
        return_value={
            'interfaces': [
                {
                    'name': 'vnet0',
                    'type': 'bridge',
                    'source': 'ovsbr0',
                    'model': 'virtio',
                    'mac': '52:54:00:aa:bb:cc',
                }
            ]
        },
    )
    def test_instance_interfaces_returns_vnic(self, interfaces) -> None:
        """实例接口接口返回 vNIC 信息。"""
        self.client.login(username='api-life', password='Str0ngPassw0rd')

        response = self.client.get(f'/api/v1/instances/{self.instance.pk}/interfaces')

        self.assertEqual(response.status_code, 200)
        body = response.json()['interfaces']
        self.assertEqual(body[0]['source'], 'ovsbr0')
        self.assertEqual(body[0]['mac'], '52:54:00:aa:bb:cc')
        interfaces.assert_called_once_with(self.instance.libvirt_domain_name)

    @override_settings(AGENT_SHARED_TOKEN='shared-secret', CONSOLE_REQUIRE_TLS=False)
    def test_instance_console_returns_opaque_session_path(self) -> None:
        self.instance.observed_state = 'RUNNING'
        self.instance.save(update_fields=['observed_state'])
        self.client.login(username='api-life', password='Str0ngPassw0rd')
        response = self.client.post(f'/api/v1/console/instances/{self.instance.pk}/sessions')
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body['type'], 'vnc')
        self.assertEqual(body['password'], self.instance.vnc_password)
        self.assertTrue(body['path'].startswith('/console-ws/'))
        self.assertNotIn('sig=', body['path'])

    def test_old_console_endpoint_does_not_issue_credentials(self) -> None:
        self.client.login(username='api-life', password='Str0ngPassw0rd')
        response = self.client.get(f'/api/v1/instances/{self.instance.pk}/console')
        self.assertEqual(response.status_code, 410)
        self.assertNotIn('password', response.json())

    def test_operator_can_delete_without_purge(self) -> None:
        """Operator 可删除实例但保留磁盘。"""
        self.client.login(username='api-life', password='Str0ngPassw0rd')

        response = self.client.delete(f'/api/v1/instances/{self.instance.pk}')

        self.assertEqual(response.status_code, 202)

    def test_operator_can_purge_disk(self) -> None:
        """学员可以在删除实例时清理磁盘。"""
        self.client.login(username='api-life', password='Str0ngPassw0rd')

        response = self.client.delete(f'/api/v1/instances/{self.instance.pk}?purge_disk=true')

        self.assertEqual(response.status_code, 202)
        task = Task.objects.get(type=TaskType.INSTANCE_DELETE)
        self.assertTrue(task.payload['purge_disk'])

    def test_admin_can_purge_disk(self) -> None:
        """Admin 可删除实例并清理磁盘。"""
        self.client.login(username='life-admin', password='Str0ngPassw0rd')

        response = self.client.delete(f'/api/v1/instances/{self.instance.pk}?purge_disk=true')

        self.assertEqual(response.status_code, 202)
        task = Task.objects.get(type=TaskType.INSTANCE_DELETE)
        self.assertTrue(task.payload['purge_disk'])
