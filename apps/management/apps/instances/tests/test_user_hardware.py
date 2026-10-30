"""Ordinary users can attach networks and manage only their own data disks."""

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.instances.device_management import execute_hardware_change
from apps.instances.models import Disk
from apps.instances.tests import test_device_management as helpers
from apps.instances.tests.helpers import make_user
from apps.networks.models import Network
from apps.tasks.models import Task


class UserHardwareTests(TestCase):
    setUp = helpers.DeviceManagementTests.setUp

    def post(self, **data):
        return self.client.post(
            f'/api/v1/operator/vms/{self.vm.pk}/hardware/', data, content_type='application/json'
        )

    def test_user_can_add_and_detach_own_data_disk_but_not_change_system_hardware(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.post(operation='disk-add', size_gib=2, bus='virtio').status_code, 202)
        task = Task.objects.get()
        change = task.payload['change']
        with patch(
            'apps.nodes.client.AgentClient.domain_hardware',
            return_value={
                'uuid': str(self.vm.uuid),
                'disks': [
                    {
                        'target': change['target'],
                        'relative_path': change['relative_path'],
                        'size_bytes': 2 * 1024**3,
                    }
                ],
            },
        ):
            execute_hardware_change(task)
        task.status = 'SUCCEEDED'
        task.save(update_fields=['status'])
        self.vm.current_task = None
        self.vm.operation_status = 'SUCCEEDED'
        self.vm.save(update_fields=['current_task', 'operation_status'])
        disk = Disk.objects.get(instance=self.vm, role='DATA')
        self.assertEqual(disk.status, 'READY')
        self.assertEqual(self.post(operation='disk-detach', disk_id=disk.pk).status_code, 202)
        detached_task = Task.objects.order_by('-created_at').first()
        with patch(
            'apps.nodes.client.AgentClient.domain_hardware',
            return_value={'uuid': str(self.vm.uuid), 'disks': []},
        ):
            execute_hardware_change(detached_task)
        detached_task.status = 'SUCCEEDED'
        detached_task.save(update_fields=['status'])
        disk.refresh_from_db()
        self.assertEqual(disk.status, 'DETACHED')
        self.assertTrue(disk.is_orphan)
        deleted = self.client.delete(
            f'/api/v1/disks/{disk.pk}', HTTP_IDEMPOTENCY_KEY='detach-then-delete'
        )
        self.assertEqual(deleted.status_code, 202, deleted.content)
        self.assertEqual(self.post(operation='compute', vcpu=4, memory_mib=1024).status_code, 403)
        self.assertEqual(
            self.post(operation='disk-resize', disk_id=disk.pk, size_gib=5).status_code, 403
        )

    def test_user_cannot_detach_system_disk(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.post(operation='disk-detach', disk_id=self.disk.pk).status_code, 409)

    def test_user_can_request_permanent_deletion_after_data_disk_is_detached(self):
        self.client.force_login(self.owner)
        disk = Disk.objects.create(
            instance=self.vm,
            role='DATA',
            name='own-data.qcow2',
            relative_path='own-data.qcow2',
            size_gib=2,
            target_dev='vdb',
            status='DETACHED',
            is_orphan=True,
        )
        response = self.client.delete(
            f'/api/v1/disks/{disk.pk}', HTTP_IDEMPOTENCY_KEY='delete-own-data'
        )
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(Task.objects.get().payload['disk_id'], disk.pk)
        self.assertEqual(disk.status, 'DETACHED')

    def test_user_can_connect_own_vm_but_not_other_vm_or_create_network(self):
        network = Network.objects.create(name='own-network')
        self.client.force_login(self.owner)
        response = self.post(operation='nic-add', network_name=network.name, model='virtio')
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(
            self.post(operation='nic-remove', mac='02:11:22:33:44:55').status_code, 403
        )
        self.assertEqual(
            self.client.post('/api/v1/networks', {'name': 'new-network'}).status_code, 403
        )
        other = make_user('other-device-owner', 'Viewer')
        self.client.force_login(other)
        self.assertEqual(
            self.post(operation='nic-add', network_name=network.name, model='virtio').status_code,
            404,
        )
        self.assertEqual(self.client.delete(f'/api/v1/disks/{self.disk.pk}').status_code, 404)

    def test_running_vm_hot_connection_requires_fresh_state_and_agent_capability(self):
        self.vm.observed_state = 'RUNNING'
        self.vm.observed_state_is_stale = False
        self.vm.observed_state_updated_at = timezone.now()
        self.vm.save()
        network = Network.objects.create(name='user-hot-network')
        self.client.force_login(self.owner)
        with patch('apps.nodes.client.AgentClient.get_json', return_value={'nic_hotplug': True}):
            response = self.post(
                operation='nic-add', network_name=network.name, model='virtio', live=True
            )
        self.assertEqual(response.status_code, 202, response.content)
        self.assertTrue(Task.objects.get().payload['change']['live'])
