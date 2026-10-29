"""实例创建服务与 API 测试。"""

from django.test import TestCase

from apps.instances.models import ReservationStatus, ResourceReservation
from apps.instances.services import create_instance
from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.tasks.models import Task, TaskType
from common.errors import AppError, ErrorCode


class CreateInstanceServiceTests(TestCase):
    """创建服务：校验、预留与入队。"""

    def setUp(self) -> None:
        """准备用户、节点与镜像。"""
        self.user = make_user('creator', 'Operator')
        self.node = make_node()
        self.image = make_image()

    def test_creates_instance_disk_task_and_reservation(self) -> None:
        """创建成功应同时生成实例、系统盘、任务与预留。"""
        instance, task = create_instance(
            user=self.user,
            name='vm-001',
            node=self.node,
            image=self.image,
            vcpu=2,
            memory_mib=2048,
            disk_gib=20,
        )

        self.assertEqual(instance.operation_status, 'PENDING')
        self.assertEqual(instance.libvirt_domain_name, f'cv-{str(instance.uuid)[:8]}')
        self.assertEqual(instance.disks.count(), 1)
        self.assertEqual(instance.disks.first().size_gib, 20)
        reservation = ResourceReservation.objects.get(instance=instance)
        self.assertEqual(reservation.status, ReservationStatus.HELD)
        self.assertEqual(reservation.disk_reserved_bytes, 20 * 1024 * 1024 * 1024)
        self.assertEqual(task.type, TaskType.INSTANCE_CREATE)
        self.assertEqual(task.status, 'PENDING')
        self.assertEqual(instance.current_task_id, task.pk)

    def test_rejects_duplicate_name_on_same_node(self) -> None:
        """同节点重名应返回 409。"""
        create_instance(
            user=self.user,
            name='vm-dup',
            node=self.node,
            image=self.image,
            vcpu=1,
            memory_mib=512,
            disk_gib=10,
        )

        with self.assertRaises(AppError) as ctx:
            create_instance(
                user=self.user,
                name='vm-dup',
                node=self.node,
                image=self.image,
                vcpu=1,
                memory_mib=512,
                disk_gib=10,
            )

        self.assertEqual(ctx.exception.code, ErrorCode.CONFLICT)

    def test_rejects_insufficient_resources(self) -> None:
        """资源不足应返回 409 并说明缺口。"""
        capacity_admin = make_user('capacity-admin', 'Admin')
        with self.assertRaises(AppError) as ctx:
            create_instance(
                user=capacity_admin,
                name='vm-big',
                node=self.node,
                image=self.image,
                vcpu=64,
                memory_mib=2048,
                disk_gib=10,
            )

        self.assertEqual(ctx.exception.code, ErrorCode.INSUFFICIENT_RESOURCE)
        self.assertIn('vcpu', ctx.exception.details['shortage'])

    def test_reservation_prevents_concurrent_oversubscription(self) -> None:
        """在途预留应占用额度，避免两次创建同时通过校验。"""
        create_instance(
            user=self.user,
            name='vm-a',
            node=self.node,
            image=self.image,
            vcpu=10,
            memory_mib=8192,
            disk_gib=10,
        )

        with self.assertRaises(AppError) as ctx:
            create_instance(
                user=self.user,
                name='vm-b',
                node=self.node,
                image=self.image,
                vcpu=10,
                memory_mib=8192,
                disk_gib=10,
            )

        self.assertEqual(ctx.exception.code, ErrorCode.INSUFFICIENT_RESOURCE)

    def test_rejects_unready_image(self) -> None:
        """非 READY 镜像不可用于创建。"""
        broken = make_image(name='broken', relative_path='iso/broken.qcow2', status='FAILED')

        with self.assertRaises(AppError) as ctx:
            create_instance(
                user=self.user,
                name='vm-x',
                node=self.node,
                image=broken,
                vcpu=1,
                memory_mib=512,
                disk_gib=10,
            )

        self.assertEqual(ctx.exception.code, ErrorCode.CONFLICT)

    def test_rejects_offline_node(self) -> None:
        """离线节点不可调度。"""
        offline = make_node(name='hv-off', status='OFFLINE')

        with self.assertRaises(AppError) as ctx:
            create_instance(
                user=self.user,
                name='vm-y',
                node=offline,
                image=self.image,
                vcpu=1,
                memory_mib=512,
                disk_gib=10,
            )

        self.assertEqual(ctx.exception.code, ErrorCode.NODE_OFFLINE)

    def test_rejects_invalid_spec(self) -> None:
        """非法名称与超限规格应返回 400。"""
        cases = [
            {'name': 'a', 'vcpu': 1, 'memory_mib': 512, 'disk_gib': 10},
            {'name': 'vm-ok', 'vcpu': 0, 'memory_mib': 512, 'disk_gib': 10},
            {'name': 'vm-ok', 'vcpu': 1, 'memory_mib': 512, 'disk_gib': 0},
            {'name': 'vm-ok', 'vcpu': 1000, 'memory_mib': 512, 'disk_gib': 10},
        ]
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(AppError) as ctx:
                    create_instance(user=self.user, node=self.node, image=self.image, **case)
                self.assertEqual(ctx.exception.code, ErrorCode.VALIDATION_ERROR)


class CreateInstanceApiTests(TestCase):
    """创建接口的权限与响应码。"""

    def setUp(self) -> None:
        """准备操作员、只读用户与资源。"""
        self.operator = make_user('api-operator', 'Operator')
        self.viewer = make_user('api-viewer', 'Viewer')
        self.node = make_node(name='hv-api')
        self.image = make_image(name='api-image', relative_path='iso/api.qcow2')

    def payload(self) -> dict:
        """构造创建请求体。"""
        return {
            'name': 'vm-api-1',
            'node': self.node.pk,
            'image': self.image.pk,
            'vcpu': 2,
            'memory_mib': 1024,
            'disk_gib': 10,
        }

    def test_unauthenticated_returns_401(self) -> None:
        """未认证应返回 401。"""
        self.assertEqual(self.client.get('/api/v1/instances').status_code, 401)

    def test_general_user_can_create_instance(self) -> None:
        """一般用户可以创建实例。"""
        self.client.login(username='api-viewer', password='Str0ngPassw0rd')

        response = self.client.post(
            '/api/v1/instances', self.payload(), content_type='application/json'
        )

        self.assertEqual(response.status_code, 202)

    def test_operator_gets_202_with_task(self) -> None:
        """创建成功应返回 202 与任务引用。"""
        self.client.login(username='api-operator', password='Str0ngPassw0rd')

        response = self.client.post(
            '/api/v1/instances', self.payload(), content_type='application/json'
        )

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body['instance']['operation_status'], 'PENDING')
        self.assertEqual(body['instance']['observed_state'], 'UNKNOWN')
        self.assertIn('status_url', body['task'])
        self.assertTrue(Task.objects.filter(type=TaskType.INSTANCE_CREATE).exists())

    def test_insufficient_resource_returns_409(self) -> None:
        """资源不足应返回 409 与缺口说明。"""
        self.client.login(username='api-operator', password='Str0ngPassw0rd')
        payload = dict(self.payload(), name='vm-huge', vcpu=64)

        response = self.client.post('/api/v1/instances', payload, content_type='application/json')

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error']['code'], 'INSUFFICIENT_RESOURCE')

    def test_viewer_cannot_list_other_users_instances(self) -> None:
        """Viewer 可以打开列表，但不能查看其他用户的实例。"""
        self.client.login(username='api-operator', password='Str0ngPassw0rd')
        self.client.post('/api/v1/instances', self.payload(), content_type='application/json')
        self.client.logout()
        self.client.login(username='api-viewer', password='Str0ngPassw0rd')

        response = self.client.get('/api/v1/instances')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 0)
