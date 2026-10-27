"""网络白名单 API 与校验测试。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.accounts.roles import sync_role_permissions
from apps.audit.models import AuditAction, AuditEvent
from apps.instances.models import Instance
from apps.instances.services import create_instance
from apps.instances.tests.helpers import make_image, make_node
from apps.networks.models import Network
from apps.networks.services import validate_network_for_instance
from common.errors import AppError, ErrorCode


class NetworkApiTests(TestCase):
    """网络白名单的权限与响应。"""

    def setUp(self) -> None:
        """同步角色并创建各角色用户。"""
        sync_role_permissions()
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(username='net-admin', password='Str0ngPassw0rd')
        self.admin.groups.add(Group.objects.get(name='Admin'))
        self.operator = user_model.objects.create_user(
            username='net-operator', password='Str0ngPassw0rd'
        )
        self.operator.groups.add(Group.objects.get(name='Operator'))
        self.viewer = user_model.objects.create_user(
            username='net-viewer', password='Str0ngPassw0rd'
        )
        self.viewer.groups.add(Group.objects.get(name='Viewer'))

    def test_unauthenticated_returns_401(self) -> None:
        """未认证应返回 401。"""
        self.assertEqual(self.client.get('/api/v1/networks').status_code, 401)

    def test_viewer_can_list_networks(self) -> None:
        """Viewer 可以查看白名单。"""
        Network.objects.create(name='app-net')
        self.client.login(username='net-viewer', password='Str0ngPassw0rd')

        response = self.client.get('/api/v1/networks')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)

    def test_operator_can_register_network(self) -> None:
        """学员可以登记网络白名单。"""
        self.client.login(username='net-operator', password='Str0ngPassw0rd')

        response = self.client.post(
            '/api/v1/networks',
            {'name': 'new-net', 'type': 'LIBVIRT_NETWORK'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Network.objects.filter(name='new-net').exists())

    def test_admin_registers_network_with_audit(self) -> None:
        """Admin 登记网络并留痕。"""
        self.client.login(username='net-admin', password='Str0ngPassw0rd')

        response = self.client.post(
            '/api/v1/networks',
            {'name': 'app-net', 'type': 'LIBVIRT_NETWORK', 'description': '业务网'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        network = Network.objects.get(name='app-net')
        self.assertTrue(network.is_usable)
        self.assertTrue(
            AuditEvent.objects.filter(
                action=AuditAction.NETWORK_CREATE, target_id=str(network.pk)
            ).exists()
        )

    def test_management_network_cannot_be_default(self) -> None:
        """管理网不能同时作为默认网络。"""
        self.client.login(username='net-admin', password='Str0ngPassw0rd')

        response = self.client.post(
            '/api/v1/networks',
            {'name': 'mgmt-net', 'is_management': True, 'is_default': True},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)

    def test_invalid_network_name_is_rejected(self) -> None:
        """非法名称返回 400。"""
        self.client.login(username='net-admin', password='Str0ngPassw0rd')

        response = self.client.post(
            '/api/v1/networks', {'name': 'bad name!'}, content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)


class NetworkValidationTests(TestCase):
    """实例创建时的网络白名单校验。"""

    def setUp(self) -> None:
        """准备用户、节点与镜像。"""
        self.user = get_user_model().objects.create_user(
            username='net-owner', password='Str0ngPassw0rd'
        )
        self.node = make_node(name='hv-net')
        self.image = make_image(name='net-image', relative_path='iso/net.qcow2')

    def test_empty_network_is_allowed(self) -> None:
        """未指定网络时不做校验。"""
        self.assertIsNone(validate_network_for_instance(''))

    def test_unknown_network_is_rejected(self) -> None:
        """白名单外的网络被拒绝。"""
        with self.assertRaises(AppError) as ctx:
            validate_network_for_instance('ghost-net')

        self.assertEqual(ctx.exception.code, ErrorCode.VALIDATION_ERROR)

    def test_management_network_is_rejected(self) -> None:
        """管理网禁止接入。"""
        Network.objects.create(name='mgmt', is_management=True)

        with self.assertRaises(AppError) as ctx:
            validate_network_for_instance('mgmt')

        self.assertIn('管理网络', ctx.exception.message)

    def test_instance_creation_uses_whitelisted_network(self) -> None:
        """白名单网络可被实例创建使用并记录名称。"""
        Network.objects.create(name='app-net')

        instance, _ = create_instance(
            user=self.user,
            name='vm-net',
            node=self.node,
            image=self.image,
            vcpu=1,
            memory_mib=512,
            disk_gib=5,
            network_name='app-net',
        )

        self.assertEqual(Instance.objects.get(pk=instance.pk).network_name, 'app-net')

    def test_instance_creation_rejects_management_network(self) -> None:
        """使用管理网创建实例应失败且不留记录。"""
        Network.objects.create(name='mgmt', is_management=True)

        with self.assertRaises(AppError) as ctx:
            create_instance(
                user=self.user,
                name='vm-mgmt',
                node=self.node,
                image=self.image,
                vcpu=1,
                memory_mib=512,
                disk_gib=5,
                network_name='mgmt',
            )

        self.assertEqual(ctx.exception.code, ErrorCode.VALIDATION_ERROR)
        self.assertFalse(Instance.objects.filter(name='vm-mgmt').exists())
