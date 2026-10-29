from unittest.mock import patch

from django.test import TestCase

from apps.instances.models import Instance, ResourceReservation
from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.tasks.models import Task
from apps.templates.models import Template, TemplateVersion


class CreationPlanTests(TestCase):
    def test_requested_start_cannot_succeed_when_agent_reports_shutoff(self):
        from apps.instances.executors import execute_instance_create
        from common.errors import AppError

        response = self.post('instances', {**self.data, 'start_after_create': True})
        self.assertEqual(response.status_code, 202, response.content)
        with (
            patch(
                'apps.nodes.client.AgentClient.get_json',
                return_value={'image_clone': True, 'iso_install': True, 'start_control': True},
            ),
            patch('apps.nodes.client.AgentClient.create_domain', return_value={'state': 'SHUTOFF'}),
            self.assertRaises(AppError),
        ):
            execute_instance_create(Task.objects.get())
        self.assertEqual(Instance.objects.get().operation_status, 'FAILED')

    def setUp(self):
        self.user = make_user('creation-plan-admin', 'Admin')
        self.client.force_login(self.user)
        self.node = make_node()
        self.image = make_image(node=self.node)
        self.data = {
            'name': 'planned-vm',
            'node': self.node.pk,
            'image': self.image.pk,
            'vcpu': 2,
            'memory_mib': 1024,
            'disk_gib': 20,
            'start_after_create': False,
            'autostart': True,
        }

    def post(self, path, data):
        return self.client.post('/api/v1/' + path, data, content_type='application/json')

    def test_preflight_is_read_only(self):
        with patch(
            'apps.nodes.client.AgentClient.get_json',
            return_value={'image_clone': True, 'iso_install': True, 'start_control': True},
        ):
            response = self.post('instances/preflight', self.data)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(Instance.objects.exists())
        self.assertFalse(Task.objects.exists())
        self.assertFalse(ResourceReservation.objects.exists())

    def test_creation_snapshot_and_start_flags(self):
        response = self.post('instances', self.data)
        self.assertEqual(response.status_code, 202, response.content)
        vm = Instance.objects.get()
        self.assertFalse(vm.creation_config['start_after_create'])
        self.assertTrue(vm.autostart)
        self.assertEqual(vm.creation_config['image']['checksum'], self.image.checksum_sha256)

    def test_new_options_change_idempotency(self):
        first = self.client.post(
            '/api/v1/instances',
            self.data,
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='plan-unique',
        )
        self.assertEqual(first.status_code, 202, first.content)
        second = self.client.post(
            '/api/v1/instances',
            {**self.data, 'start_after_create': True},
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='plan-unique',
        )
        self.assertEqual(second.status_code, 409, second.content)

    def test_private_template_not_listed_for_other_user(self):
        Template.objects.create(
            name='private-plan',
            vcpu=2,
            memory_mib=1024,
            disk_gib=20,
            is_public=False,
            created_by=self.user,
        )
        other = make_user('other-plan-user', 'Viewer')
        self.client.force_login(other)
        self.assertEqual(self.client.get('/api/v1/templates').json()['count'], 0)

    def test_published_template_locks_image_and_pins_values(self):
        parent = Template.objects.create(
            name='published-plan',
            vcpu=2,
            memory_mib=1024,
            disk_gib=20,
            is_public=True,
            created_by=self.user,
        )
        draft = self.post(
            f'templates/{parent.pk}/versions',
            {
                'configuration': {'image': self.image.pk},
                'constraints': {'locked': ['image'], 'bounds': {'vcpu': {'min': 1, 'max': 4}}},
            },
        )
        self.assertEqual(draft.status_code, 201, draft.content)
        version = draft.json()['id']
        published = self.post(f'template-versions/{version}/publish', {})
        self.assertEqual(published.status_code, 200, published.content)
        parent.vcpu = 8
        parent.save()
        config = {'name': self.data['name'], 'template_version': version}
        response = self.post('instances', config)
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(Instance.objects.get().vcpu, 2)
        other = make_image(name='other-image', relative_path='other.qcow2', node=self.node)
        blocked = self.post('instances', {**config, 'name': 'blocked-plan', 'image': other.pk})
        self.assertEqual(blocked.status_code, 400, blocked.content)
        self.assertTrue(TemplateVersion.objects.get(pk=version).published)

    def test_all_disks_reserved_and_pending_instance_not_double_counted(self):
        from apps.instances.services import available_resources
        from common.quota import quota_for

        response = self.post('instances', {**self.data, 'data_disks': [10, 15]})
        self.assertEqual(response.status_code, 202, response.content)
        vm = Instance.objects.get()
        self.assertEqual(vm.disks.count(), 3)
        self.assertEqual(quota_for(self.user)['used']['disk_gib'], 45)
        self.assertEqual(ResourceReservation.objects.get().disk_reserved_bytes, 45 * 1024**3)
        self.assertEqual(available_resources(self.node)['vcpu'], self.node.cpu_total - 2)
        self.assertEqual(vm.desired_state, 'SHUTOFF')

    def test_invalid_topology_rejected_without_writes(self):
        response = self.post(
            'instances', {**self.data, 'hardware': {'sockets': 1, 'cores': 3, 'threads': 1}}
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(Instance.objects.exists())

    def test_ordinary_user_cannot_set_performance_limits(self):
        user = make_user('creation-ordinary', 'Viewer')
        self.client.force_login(user)
        response = self.post('instances', {**self.data, 'hardware': {'cpu_quota_percent': 100}})
        self.assertEqual(response.status_code, 400, response.content)

    def test_unknown_hardware_fields_rejected(self):
        response = self.post('instances', {**self.data, 'hardware': {'raw_xml': '<hostdev/>'}})
        self.assertEqual(response.status_code, 400, response.content)

    def test_cloud_init_requires_reviewed_image_and_key(self):
        import base64

        blob = (11).to_bytes(4, 'big') + b'ssh-ed25519' + (32).to_bytes(4, 'big') + b'x' * 32
        initialization = {
            'username': 'cloudvirt',
            'ssh_public_keys': ['ssh-ed25519 ' + base64.b64encode(blob).decode()],
        }
        response = self.post('instances', {**self.data, 'initialization': initialization})
        self.assertEqual(response.status_code, 400, response.content)
        self.image.supports_cloud_init = True
        self.image.save()
        response = self.post('instances', {**self.data, 'initialization': initialization})
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(Instance.objects.get().initialization_status, 'PENDING')

    def test_revoked_actor_cannot_execute_queued_creation(self):
        from apps.instances.executors import execute_instance_create
        from common.errors import AppError

        response = self.post('instances', self.data)
        self.assertEqual(response.status_code, 202, response.content)
        self.user.groups.clear()
        with self.assertRaises(AppError) as error:
            execute_instance_create(Task.objects.get())
        self.assertEqual(error.exception.code, 'PERMISSION_DENIED')
