"""磁盘登记与孤儿扫描测试。"""

from django.test import TestCase

from apps.images.models import Image, ImageStatus
from apps.instances.models import Disk, Instance, ObservedState
from apps.monitoring.models import Alert, DiffKind, DiffResolution, ReconciliationRun
from apps.monitoring.services import reconcile_node
from apps.nodes.models import Node, NodeStatus
from apps.nodes.tests.fakes import FakeAgentClient

GIB = 1024 * 1024 * 1024


class DiskReconcileTests(TestCase):
    """磁盘与数据库记录的一致性检查。"""

    def setUp(self) -> None:
        """准备节点、镜像、实例与一块系统盘。"""
        self.node = Node.objects.create(
            name='disk-hv',
            endpoint='http://127.0.0.1:9100',
            status=NodeStatus.ONLINE,
            cpu_total=8,
            memory_total_mib=16384,
            storage_free_bytes=100 * GIB,
        )
        image = Image.objects.create(
            name='disk-image',
            format='QCOW2',
            relative_path='iso/disk.qcow2',
            status=ImageStatus.READY,
        )
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(username='disk-user', password='Str0ngPassw0rd')
        self.instance = Instance.objects.create(
            name='vm-disk',
            libvirt_domain_name='cv-disk',
            node=self.node,
            image=image,
            vcpu=1,
            memory_mib=512,
            disk_gib=10,
            observed_state=ObservedState.RUNNING,
            created_by=user,
        )
        self.disk = Disk.objects.create(
            instance=self.instance,
            name='vm-disk-system.qcow2',
            relative_path='vm-disk-system.qcow2',
            size_gib=10,
        )

    def _agent(self, files: list[dict]) -> FakeAgentClient:
        """构造返回指定磁盘文件列表的 Agent 替身。"""
        agent = FakeAgentClient()
        agent.domains = lambda: [{'name': 'cv-disk', 'state': 'RUNNING'}]
        agent._disk_files = files
        return agent

    def test_missing_disk_file_is_reported(self) -> None:
        """磁盘记录缺少对应文件时应报告且不删除记录。"""
        run = ReconciliationRun.objects.create(scope='test')

        summary = reconcile_node(self.node, client=self._agent([]), run=run)

        self.assertEqual(summary['disk_missing'], 1)
        diff = run.diffs.get(kind=DiffKind.DISK_FILE_MISSING)
        self.assertEqual(diff.resource_id, str(self.disk.pk))
        self.assertEqual(diff.resolution, DiffResolution.MANUAL)
        self.assertTrue(self.disk is not None and Disk.objects.filter(pk=self.disk.pk).exists())
        self.assertTrue(Alert.objects.filter(type='DISK_FILE_MISSING', status='ACTIVE').exists())

    def test_orphan_disk_file_is_reported(self) -> None:
        """未登记的磁盘文件应报告，且不影响既有记录。"""
        files = [
            {'name': 'vm-disk-system.qcow2', 'virtual_size_bytes': 10 * GIB},
            {'name': 'stranger.qcow2', 'virtual_size_bytes': 1 * GIB},
        ]
        run = ReconciliationRun.objects.create(scope='test')

        summary = reconcile_node(self.node, client=self._agent(files), run=run)

        self.assertEqual(summary['disk_orphan'], 1)
        diff = run.diffs.get(kind=DiffKind.DISK_NOT_IN_DB)
        self.assertEqual(diff.resource_id, 'stranger.qcow2')
        self.assertEqual(diff.resolution, DiffResolution.MANUAL)
        self.assertFalse(Disk.objects.filter(name='stranger.qcow2').exists())

    def test_size_mismatch_is_reported(self) -> None:
        """虚拟容量与记录不一致时应报告。"""
        files = [{'name': 'vm-disk-system.qcow2', 'virtual_size_bytes': 20 * GIB}]
        run = ReconciliationRun.objects.create(scope='test')

        summary = reconcile_node(self.node, client=self._agent(files), run=run)

        self.assertEqual(summary['disk_size_mismatch'], 1)
        diff = run.diffs.get(kind=DiffKind.DISK_SIZE_MISMATCH)
        self.assertEqual(diff.detail['expected_bytes'], 10 * GIB)
        self.assertEqual(diff.detail['actual_bytes'], 20 * GIB)

    def test_consistent_disk_produces_no_diff(self) -> None:
        """一致时应无磁盘相关差异。"""
        files = [{'name': 'vm-disk-system.qcow2', 'virtual_size_bytes': 10 * GIB}]
        run = ReconciliationRun.objects.create(scope='test')

        summary = reconcile_node(self.node, client=self._agent(files), run=run)

        self.assertEqual(summary['disk_missing'], 0)
        self.assertEqual(summary['disk_orphan'], 0)
        self.assertEqual(summary['disk_size_mismatch'], 0)

    def test_disk_scan_failure_does_not_break_domain_reconcile(self) -> None:
        """磁盘清单不可用时，域对账仍然完成。"""
        agent = FakeAgentClient()
        agent.domains = lambda: [{'name': 'cv-disk', 'state': 'RUNNING'}]
        agent.list_disks = self._raise_missing

        run = ReconciliationRun.objects.create(scope='test')
        summary = reconcile_node(self.node, client=agent, run=run)

        self.assertEqual(summary['drift'], 0)
        self.assertEqual(summary['disk_missing'], 0)

    def _raise_missing(self) -> list[dict]:
        """模拟旧版本 Agent 返回 404（客户端映射为 AppError）。"""
        from common.errors import AppError, ErrorCode

        raise AppError(ErrorCode.OPERATION_FAILED, '节点 Agent 拒绝了该操作')

    def test_disk_list_api_filters_by_instance(self) -> None:
        """磁盘接口支持按实例过滤，并受实例查看权限约束。"""
        from django.contrib.auth.models import Group

        from apps.accounts.roles import sync_role_permissions

        sync_role_permissions()
        from django.contrib.auth import get_user_model

        viewer = get_user_model().objects.create_user(
            username='disk-viewer', password='Str0ngPassw0rd'
        )
        viewer.groups.add(Group.objects.get(name='Viewer'))
        self.client.login(username='disk-viewer', password='Str0ngPassw0rd')

        response = self.client.get(f'/api/v1/disks?instance={self.instance.pk}')

        self.assertEqual(response.status_code, 200)
        body = response.json()['results']
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]['instance'], self.instance.pk)
        self.assertEqual(body[0]['instance_name'], self.instance.name)
