"""镜像导入与删除服务测试。"""

from unittest import mock

from django.test import TestCase

from apps.images.models import Image, ImageStatus
from apps.images.services import delete_image, import_image, validate_relative_path
from apps.nodes.models import Node, NodeStatus
from common.errors import AppError, ErrorCode

GOOD_INFO = {
    'format': 'QCOW2',
    'size_bytes': 196640,
    'virtual_size_bytes': 2147483648,
    'checksum_sha256': 'a' * 64,
}


class ImageServiceTests(TestCase):
    """镜像服务用例。"""

    def setUp(self) -> None:
        """创建在线节点。"""
        self.node = Node.objects.create(
            name='image-node', endpoint='http://127.0.0.1:9100', status=NodeStatus.ONLINE
        )

    def test_relative_path_validation(self) -> None:
        """拒绝绝对路径、目录穿越与非法字符。"""
        for bad in ['/etc/passwd', '../secret.qcow2', 'a/../../b', 'bad name.img', '']:
            with self.subTest(bad=bad):
                with self.assertRaises(AppError):
                    validate_relative_path(bad)
        self.assertEqual(validate_relative_path('iso/ubuntu-24.04.iso'), 'iso/ubuntu-24.04.iso')

    def test_import_success(self) -> None:
        """导入成功应写入真实检测结果并置为 READY。"""
        with mock.patch('apps.nodes.client.AgentClient.inspect_image', return_value=GOOD_INFO):
            image = import_image(
                name='ubuntu-24.04', node=self.node, relative_path='iso/ubuntu.qcow2'
            )

        self.assertEqual(image.status, ImageStatus.READY)
        self.assertEqual(image.format, 'QCOW2')
        self.assertEqual(image.size_bytes, 196640)
        self.assertEqual(image.virtual_size_bytes, 2147483648)
        self.assertEqual(image.checksum_sha256, 'a' * 64)
        self.assertTrue(image.is_ready)

    def test_import_rejects_unsupported_format(self) -> None:
        """不支持的格式应记录失败并抛出校验错误。"""
        info = dict(GOOD_INFO, format='VMDK')
        with mock.patch('apps.nodes.client.AgentClient.inspect_image', return_value=info):
            with self.assertRaises(AppError) as ctx:
                import_image(name='bad-format', node=self.node, relative_path='x.vmdk')

        self.assertEqual(ctx.exception.code, ErrorCode.VALIDATION_ERROR)
        failed = Image.objects.get(name='bad-format')
        self.assertEqual(failed.status, ImageStatus.FAILED)

    def test_import_records_agent_failure(self) -> None:
        """Agent 检查失败应留下失败记录。"""
        with mock.patch(
            'apps.nodes.client.AgentClient.inspect_image',
            side_effect=AppError(ErrorCode.NOT_FOUND, '文件不存在'),
        ):
            with self.assertRaises(AppError):
                import_image(name='missing', node=self.node, relative_path='nope.qcow2')

        failed = Image.objects.get(name='missing')
        self.assertEqual(failed.status, ImageStatus.FAILED)
        self.assertEqual(failed.error_code, ErrorCode.NOT_FOUND)

    def test_import_requires_online_node(self) -> None:
        """离线节点不得导入镜像，且不留脏记录。"""
        self.node.status = NodeStatus.OFFLINE
        self.node.save(update_fields=['status'])

        with self.assertRaises(AppError) as ctx:
            import_image(name='offline-image', node=self.node, relative_path='x.qcow2')

        self.assertEqual(ctx.exception.code, ErrorCode.NODE_OFFLINE)
        self.assertFalse(Image.objects.filter(name='offline-image').exists())

    def test_delete_purges_file(self) -> None:
        """删除默认请求 Agent 清理文件并软删除记录。"""
        with mock.patch('apps.nodes.client.AgentClient.inspect_image', return_value=GOOD_INFO):
            image = import_image(name='to-delete', node=self.node, relative_path='del.qcow2')

        with mock.patch('apps.nodes.client.AgentClient.delete_image', return_value={}) as call:
            delete_image(image, purge_file=True, node=self.node)

        call.assert_called_once_with('del.qcow2')
        image.refresh_from_db()
        self.assertTrue(image.is_deleted)

    def test_delete_blocked_when_image_in_use(self) -> None:
        """被实例引用的镜像禁止删除。"""
        from django.contrib.auth import get_user_model

        from apps.instances.models import Instance, ObservedState

        with mock.patch('apps.nodes.client.AgentClient.inspect_image', return_value=GOOD_INFO):
            image = import_image(name='in-use', node=self.node, relative_path='in-use.qcow2')
        user = get_user_model().objects.create_user(username='img-owner', password='Str0ngPassw0rd')
        Instance.objects.create(
            name='vm-uses-image',
            libvirt_domain_name='cv-uses-img',
            node=self.node,
            image=image,
            vcpu=1,
            memory_mib=512,
            disk_gib=5,
            observed_state=ObservedState.RUNNING,
            created_by=user,
        )

        with self.assertRaises(AppError) as ctx:
            delete_image(image, purge_file=False)

        self.assertEqual(ctx.exception.code, ErrorCode.IMAGE_IN_USE)
        image.refresh_from_db()
        self.assertFalse(image.is_deleted)

    def test_delete_without_available_node(self) -> None:
        """没有可用节点时删除应失败并保留记录。"""
        with mock.patch('apps.nodes.client.AgentClient.inspect_image', return_value=GOOD_INFO):
            image = import_image(name='orphan', node=self.node, relative_path='o.qcow2')
        Node.objects.all().update(status=NodeStatus.OFFLINE)

        with self.assertRaises(AppError):
            delete_image(image, purge_file=True)

        image.refresh_from_db()
        self.assertEqual(image.status, ImageStatus.FAILED)
        self.assertFalse(image.is_deleted)
