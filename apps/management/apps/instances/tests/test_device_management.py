from unittest.mock import patch

from django.test import TestCase

from apps.instances.device_management import execute_hardware_change
from apps.instances.models import Disk, Instance, ResourceReservation
from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.networks.models import InstanceNIC, IPLease, IPPool, Network
from apps.tasks.models import Task
from common.errors import AppError, ErrorCode


class DeviceManagementTests(TestCase):
    @patch('apps.instances.device_management.AgentClient')
    def test_iso_mount_is_task_backed_and_records_reference(self, agent):
        iso = make_image(
            name='install-media', node=self.node, format='ISO', relative_path='install.iso'
        )
        response = self.post(operation='cdrom-set', target='sda', image_id=iso.pk)
        self.assertEqual(response.status_code, 202, response.content)
        task = Task.objects.get()
        agent.return_value.domain_hardware.return_value = {
            'uuid': str(self.vm.uuid),
            'cdroms': [{'target': 'sda', 'mounted': True}],
        }
        execute_hardware_change(task)
        self.vm.refresh_from_db()
        self.assertEqual(self.vm.creation_config['installation_media'], iso.pk)
        self.assertEqual(ResourceReservation.objects.get(task=task).status, 'COMMITTED')

    def test_iso_operations_reject_running_vm_and_non_iso(self):
        image = make_image(name='not-iso-media', relative_path='not-iso.qcow2', node=self.node)
        self.assertEqual(
            self.post(operation='cdrom-set', target='sda', image_id=image.pk).status_code, 404
        )
        Instance.objects.filter(pk=self.vm.pk).update(observed_state='RUNNING')
        self.assertEqual(self.post(operation='cdrom-remove', target='sda').status_code, 409)

    def test_response_loss_reuses_completed_task_instead_of_allocating_another_disk(self):
        data = {'operation': 'disk-add', 'size_gib': 2, 'bus': 'virtio'}
        first = self.client.post(
            self.url, data, content_type='application/json', HTTP_IDEMPOTENCY_KEY='stable-request'
        )
        self.assertEqual(first.status_code, 202, first.content)
        task = Task.objects.get()
        task.status = 'SUCCEEDED'
        task.save(update_fields=['status'])
        Instance.objects.filter(pk=self.vm.pk).update(observed_state='RUNNING')
        second = self.client.post(
            self.url, data, content_type='application/json', HTTP_IDEMPOTENCY_KEY='stable-request'
        )
        self.assertEqual(second.status_code, 202, second.content)
        self.assertEqual(second.json()['task']['id'], first.json()['task']['id'])
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(self.vm.disks.filter(role='DATA').count(), 1)
        changed = self.client.post(
            self.url,
            {**data, 'size_gib': 3},
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='stable-request',
        )
        self.assertEqual(changed.status_code, 409)

    def test_cancel_unstarted_hardware_releases_only_unstarted_resources(self):
        self.assertEqual(self.post(operation='disk-add', size_gib=2, bus='virtio').status_code, 202)
        task = Task.objects.get()
        response = self.client.post(f'/api/v1/tasks/{task.pk}/cancel')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(ResourceReservation.objects.get().status, 'RELEASED')
        self.assertEqual(self.vm.disks.get(role='DATA').status, 'DELETED')

    def test_retry_started_hardware_cannot_discard_reservation_by_cancel(self):
        self.assertEqual(self.post(operation='disk-add', size_gib=2, bus='virtio').status_code, 202)
        task = Task.objects.get()
        task.payload['execution_started'] = True
        task.save(update_fields=['payload'])
        response = self.client.post(f'/api/v1/tasks/{task.pk}/cancel')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(ResourceReservation.objects.get().status, 'HELD')

    def test_quota_checks_resource_owner_instead_of_administrator(self):
        from apps.accounts.models import UserProfile

        profile, _ = UserProfile.objects.get_or_create(user=self.owner)
        profile.quota_overrides = {'vcpu': 2}
        profile.save(update_fields=['quota_overrides'])
        response = self.post(operation='compute', vcpu=3, memory_mib=1024)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertIn('配额', response.json()['error']['message'])

    def test_pending_cpu_delta_counts_toward_owner_quota(self):
        from apps.accounts.models import UserProfile

        profile, _ = UserProfile.objects.get_or_create(user=self.owner)
        profile.quota_overrides = {'vcpu': 5}
        profile.save(update_fields=['quota_overrides'])
        self.assertEqual(self.post(operation='compute', vcpu=4, memory_mib=1024).status_code, 202)
        second = Instance.objects.create(
            name='second-vm',
            libvirt_domain_name='cv-second',
            node=self.node,
            image=self.vm.image,
            created_by=self.owner,
            vcpu=1,
            memory_mib=512,
            disk_gib=1,
            observed_state='SHUTOFF',
            observed_state_is_stale=False,
        )
        response = self.client.post(
            f'/api/v1/admin/vms/{second.pk}/hardware/',
            {'operation': 'compute', 'vcpu': 2, 'memory_mib': 512},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 409, response.content)
        self.assertIn('配额', response.json()['error']['message'])

    def setUp(self):
        self.admin = make_user('device-admin', 'Admin')
        self.owner = make_user('device-owner', 'Operator')
        self.node = make_node()
        self.vm = Instance.objects.create(
            name='device-vm',
            libvirt_domain_name='cv-devices',
            node=self.node,
            image=make_image(node=self.node),
            created_by=self.owner,
            vcpu=2,
            memory_mib=1024,
            disk_gib=10,
            observed_state='SHUTOFF',
            observed_state_is_stale=False,
        )
        self.disk = Disk.objects.create(
            instance=self.vm,
            name='sys.qcow2',
            relative_path='sys.qcow2',
            size_gib=10,
            status='READY',
            role='SYSTEM',
            target_dev='vda',
        )
        self.client.force_login(self.admin)
        self.url = f'/api/v1/admin/vms/{self.vm.pk}/hardware/'

    def post(self, **data):
        return self.client.post(self.url, data, content_type='application/json')

    def run_task(self, result=None):
        task = Task.objects.get()
        change = task.payload['change']
        result = result or {
            'uuid': str(self.vm.uuid),
            'vcpu': change.get('vcpu', 2),
            'memory_mib': change.get('memory_mib', 1024),
            'disks': [],
            'nics': [],
        }
        with patch('apps.nodes.client.AgentClient.domain_hardware', return_value=result):
            value = execute_hardware_change(task)
        task.status = 'SUCCEEDED'
        task.save(update_fields=['status'])
        return value

    def test_compute_applies_only_verified_result_and_commits_reservation(self):
        self.assertEqual(self.post(operation='compute', vcpu=4, memory_mib=2048).status_code, 202)
        self.run_task()
        self.vm.refresh_from_db()
        self.assertEqual((self.vm.vcpu, self.vm.memory_mib), (4, 2048))
        self.assertEqual(ResourceReservation.objects.get().status, 'COMMITTED')

    def test_disk_add_allocates_stable_file_and_verifies_before_ready(self):
        self.assertEqual(self.post(operation='disk-add', size_gib=20, bus='sata').status_code, 202)
        task = Task.objects.get()
        change = task.payload['change']
        self.assertEqual(change['target'], 'sdc')
        self.assertNotIn('/', change['relative_path'])
        self.run_task(
            {
                'uuid': str(self.vm.uuid),
                'disks': [
                    {
                        'target': 'sdc',
                        'relative_path': change['relative_path'],
                        'size_bytes': 20 * 1024**3,
                    }
                ],
                'nics': [],
            }
        )
        self.assertEqual(self.vm.disks.get(role='DATA').status, 'READY')

    def test_failure_preserves_resources_and_blocks_new_operation(self):
        self.assertEqual(
            self.post(operation='disk-add', size_gib=20, bus='virtio').status_code, 202
        )
        task = Task.objects.get()
        with (
            patch(
                'apps.nodes.client.AgentClient.domain_hardware',
                side_effect=AppError(ErrorCode.COMMAND_TIMEOUT),
            ),
            self.assertRaises(AppError),
        ):
            execute_hardware_change(task)
        task.status = 'FAILED'
        task.save(update_fields=['status'])
        self.assertEqual(ResourceReservation.objects.get().status, 'HELD')
        self.assertEqual(self.vm.disks.get(role='DATA').status, 'CREATING')
        self.assertEqual(self.post(operation='compute', vcpu=3, memory_mib=2048).status_code, 409)

    def test_regular_user_cannot_change_own_hardware_even_with_builtin_change_permission(self):
        from django.contrib.auth.models import Permission

        self.owner.user_permissions.add(
            Permission.objects.get(content_type__app_label='instances', codename='change_instance')
        )
        self.client.force_login(self.owner)
        url = f'/api/v1/operator/vms/{self.vm.pk}/hardware/'
        response = self.client.post(
            url,
            {'operation': 'compute', 'vcpu': 3, 'memory_mib': 2048},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Task.objects.exists())

    def test_running_or_stale_and_system_disk_removal_are_rejected(self):
        self.assertEqual(self.post(operation='disk-detach', disk_id=self.disk.pk).status_code, 409)
        Instance.objects.filter(pk=self.vm.pk).update(observed_state='RUNNING')
        self.assertEqual(
            self.post(operation='nic-remove', mac='02:00:00:00:00:01').status_code, 409
        )
        Instance.objects.filter(pk=self.vm.pk).update(
            observed_state='SHUTOFF', observed_state_is_stale=True
        )
        self.assertEqual(self.post(operation='compute', vcpu=3, memory_mib=2048).status_code, 409)

    def test_disk_shrink_and_unknown_parameters_are_rejected(self):
        self.assertEqual(
            self.post(operation='disk-resize', disk_id=self.disk.pk, size_gib=5).status_code, 400
        )
        self.assertEqual(
            self.post(
                operation='disk-add', size_gib=5, bus='virtio', relative_path='/etc/passwd'
            ).status_code,
            400,
        )
        self.assertFalse(Task.objects.exists())

    def test_owner_quota_and_node_capacity_enforced(self):
        from apps.infrastructure.configuration import configuration

        limit = configuration()['quota']['vcpu']
        Instance.objects.filter(pk=self.vm.pk).update(vcpu=limit)
        response = self.post(operation='compute', vcpu=limit + 1, memory_mib=1024)
        self.assertIn(response.status_code, (400, 409))
        self.assertFalse(Task.objects.exists())

    def test_active_task_prevents_duplicate(self):
        self.assertEqual(self.post(operation='compute', vcpu=3, memory_mib=2048).status_code, 202)
        self.assertEqual(self.post(operation='compute', vcpu=4, memory_mib=2048).status_code, 409)
        self.assertEqual(Task.objects.count(), 1)

    def test_network_whitelist_and_static_lease_protection(self):
        network = Network.objects.create(name='private-net')
        nic = InstanceNIC.objects.create(
            instance=self.vm, network=network, device_id='nic0', mac='02:00:00:00:00:01'
        )
        pool = IPPool.objects.create(
            network=network, name='p', first_ip='10.0.0.2', last_ip='10.0.0.10', gateway='10.0.0.1'
        )
        IPLease.objects.create(nic=nic, pool=pool, network=network, address='10.0.0.2')
        self.assertEqual(self.post(operation='nic-remove', mac=nic.mac).status_code, 409)
        self.assertEqual(
            self.post(
                operation='nic-add', network_name='not-registered', model='virtio'
            ).status_code,
            400,
        )
        self.assertFalse(Task.objects.exists())

    def test_unverified_result_never_marks_success(self):
        self.assertEqual(self.post(operation='compute', vcpu=3, memory_mib=2048).status_code, 202)
        with (
            patch(
                'apps.nodes.client.AgentClient.domain_hardware',
                return_value={'uuid': str(self.vm.uuid), 'vcpu': 2, 'memory_mib': 1024},
            ),
            self.assertRaises(AppError),
        ):
            execute_hardware_change(Task.objects.get())
        self.vm.refresh_from_db()
        self.assertEqual(self.vm.vcpu, 2)
        self.assertEqual(self.vm.operation_status, 'FAILED')
