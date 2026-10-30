from django.test import TestCase

from apps.instances.disk_cleanup import eligible
from apps.instances.models import Disk, Instance
from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.tasks.models import Task


class DiskSourceTests(TestCase):
    def setUp(self):
        self.admin = make_user('source-admin', 'Admin')
        self.user = make_user('source-user', 'Operator')
        self.node = make_node()
        self.image = make_image(node=self.node)
        self.old = Instance.objects.create(
            name='retained-old',
            node=self.node,
            image=self.image,
            vcpu=2,
            memory_mib=1024,
            disk_gib=10,
            is_deleted=True,
            created_by=self.admin,
        )
        self.disk = Disk.objects.create(
            instance=self.old,
            name='retained.qcow2',
            relative_path='retained.qcow2',
            role='SYSTEM',
            status='DETACHED',
            is_orphan=True,
            size_gib=10,
        )
        self.payload = {
            'name': 'source-clone',
            'node': self.node.pk,
            'existing_system_disk': self.disk.pk,
            'vcpu': 2,
            'memory_mib': 1024,
            'disk_gib': 10,
            'start_after_create': False,
        }
        self.client.force_login(self.admin)

    def test_clone_uses_independent_disk_and_reserves_source_against_deletion(self):
        response = self.client.post(
            '/api/v1/instances',
            self.payload,
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='source-key',
        )
        self.assertEqual(response.status_code, 202, response.content)
        vm = Instance.objects.get(name='source-clone')
        self.assertNotEqual(vm.disks.get(role='SYSTEM').relative_path, self.disk.relative_path)
        self.assertEqual(vm.creation_config['source_disk']['id'], self.disk.pk)
        self.disk.refresh_from_db()
        self.assertEqual(self.disk.instance_id, self.old.pk)
        self.assertFalse(eligible(self.disk))
        repeated = self.client.post(
            '/api/v1/instances',
            self.payload,
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='source-key',
        )
        self.assertEqual(repeated.status_code, 202, repeated.content)
        self.assertEqual(Task.objects.filter(type='INSTANCE_CREATE').count(), 1)

    def test_user_cannot_list_or_forge_source(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/api/v1/instances/system-disk-sources').status_code, 403)
        self.assertEqual(
            self.client.post(
                '/api/v1/instances', self.payload, content_type='application/json'
            ).status_code,
            403,
        )
        self.assertFalse(Instance.objects.filter(name='source-clone').exists())

    def test_attached_deleted_wrong_node_and_shrinking_are_rejected(self):
        self.disk.is_orphan = False
        self.disk.save()
        self.assertEqual(
            self.client.post(
                '/api/v1/instances', self.payload, content_type='application/json'
            ).status_code,
            404,
        )
        self.disk.is_orphan = True
        self.disk.save()
        other = make_node(name='source-other')
        for overrides in [
            {'node': other.pk},
            {'disk_gib': 5},
            {'template_version': 999},
            {'initialization': {'username': 'test'}},
        ]:
            response = self.client.post(
                '/api/v1/instances', {**self.payload, **overrides}, content_type='application/json'
            )
            self.assertIn(response.status_code, [400, 409], response.content)
        self.disk.status = 'DELETED'
        self.disk.save()
        self.assertEqual(
            self.client.get('/api/v1/instances/system-disk-sources').json()['results'], []
        )


class DirectDiskFileTests(TestCase):
    def setUp(self):
        self.admin = make_user('direct-admin', 'Admin')
        self.user = make_user('direct-user', 'Operator')
        self.node = make_node(name='direct-node')
        self.client.force_login(self.admin)
        self.data = {
            'name': 'vm-direct',
            'node': self.node.pk,
            'existing_system_file': 'systems/installed.qcow2',
            'vcpu': 2,
            'memory_mib': 1024,
            'disk_gib': 1,
            'start_after_create': False,
        }

    def test_unregistered_file_needs_no_image_and_is_used_without_cloning(self):
        from unittest.mock import patch

        from apps.instances.executors import execute_instance_create

        with patch(
            'apps.nodes.client.AgentClient.request_json',
            return_value={'format': 'QCOW2', 'virtual_size_bytes': 1024**3},
        ):
            response = self.client.post(
                '/api/v1/admin/vms/',
                self.data,
                content_type='application/json',
                HTTP_IDEMPOTENCY_KEY='direct-key',
            )
        self.assertEqual(response.status_code, 202, response.content)
        vm = Instance.objects.get(name='vm-direct')
        self.assertIsNone(vm.image_id)
        self.assertEqual(vm.disks.get(role='SYSTEM').relative_path, 'systems/installed.qcow2')
        self.assertEqual(vm.disks.get(role='SYSTEM').name, 'installed.qcow2')
        self.assertEqual(vm.reservations.get().disk_reserved_bytes, 0)
        with patch('apps.instances.executors.AgentClient') as client:
            client.return_value.get_json.return_value = {
                'existing_disk_attach': True,
                'image_clone': True,
                'iso_install': True,
                'start_control': True,
            }
            client.return_value.create_domain.return_value = {'state': 'SHUTOFF'}
            execute_instance_create(vm.current_task)
            sent = client.return_value.create_domain.call_args.args[0]
            self.assertTrue(sent['use_existing_disk'])
            self.assertEqual(sent['disk_relative_path'], self.data['existing_system_file'])
            self.assertEqual(sent['image_relative_path'], '')
        vm.refresh_from_db()
        self.assertEqual(vm.operation_status, 'SUCCEEDED')
        self.assertEqual(self.client.get(f'/api/v1/admin/vms/{vm.pk}/').status_code, 200)

    def test_admin_only_paths_and_duplicate_files_are_enforced(self):
        from unittest.mock import patch

        self.client.force_login(self.user)
        self.assertEqual(
            self.client.post(
                '/api/v1/instances', self.data, content_type='application/json'
            ).status_code,
            403,
        )
        self.client.force_login(self.admin)
        for path in ['/etc/disk.qcow2', '../disk.qcow2', 'a/../b.qcow2']:
            response = self.client.post(
                '/api/v1/instances',
                {**self.data, 'existing_system_file': path},
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 400, response.content)
        with patch(
            'apps.nodes.client.AgentClient.request_json',
            return_value={'format': 'QCOW2', 'virtual_size_bytes': 1024**3},
        ):
            response = self.client.post(
                '/api/v1/instances', self.data, content_type='application/json'
            )
            self.assertEqual(response.status_code, 202, response.content)
            response = self.client.post(
                '/api/v1/instances',
                {**self.data, 'name': 'duplicate-direct'},
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 409, response.content)
        self.assertFalse(Instance.objects.filter(name='duplicate-direct').exists())


class CloneModeTests(TestCase):
    setUp = DirectDiskFileTests.setUp

    def test_full_and_linked_file_modes_create_independent_paths_and_task_mode(self):
        from unittest.mock import patch

        from apps.instances.executors import execute_instance_create

        for mode in ['full', 'linked']:
            data = {**self.data, 'name': f'clone-{mode}', 'clone_mode': mode, 'disk_gib': 2}
            with patch(
                'apps.nodes.client.AgentClient.request_json',
                return_value={'format': 'QCOW2', 'virtual_size_bytes': 1024**3},
            ):
                response = self.client.post(
                    '/api/v1/instances', data, content_type='application/json'
                )
            self.assertEqual(response.status_code, 202, response.content)
            vm = Instance.objects.get(name=f'clone-{mode}')
            self.assertNotEqual(
                vm.disks.get(role='SYSTEM').relative_path, data['existing_system_file']
            )
            self.assertEqual(vm.reservations.get().disk_reserved_bytes, 2 * 1024**3)
            with patch('apps.instances.executors.AgentClient') as client:
                client.return_value.get_json.return_value = {
                    'existing_disk_attach': True,
                    'linked_clone': True,
                    'image_clone': True,
                    'iso_install': True,
                    'start_control': True,
                }
                client.return_value.create_domain.return_value = {'state': 'SHUTOFF'}
                execute_instance_create(vm.current_task)
                sent = client.return_value.create_domain.call_args.args[0]
                self.assertNotIn('use_existing_disk', sent)
                self.assertEqual(sent['source_disk_relative_path'], data['existing_system_file'])
                self.assertEqual(sent.get('clone_mode', 'full'), mode)

    def test_invalid_mode_and_iso_linked_clone_are_rejected(self):
        response = self.client.post(
            '/api/v1/instances', {**self.data, 'clone_mode': 'bad'}, content_type='application/json'
        )
        self.assertEqual(response.status_code, 400, response.content)
        image = make_image(node=self.node, format='ISO')
        data = {k: v for k, v in self.data.items() if k != 'existing_system_file'}
        response = self.client.post(
            '/api/v1/instances',
            {**data, 'image': image.pk, 'clone_mode': 'linked'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400, response.content)
