from unittest.mock import patch

from django.test import TestCase

from apps.instances.display import execute_instance_display
from apps.instances.hardware import HardwareSerializer
from apps.instances.models import Instance
from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.tasks.models import Task
from common.errors import AppError, ErrorCode


class DisplayTests(TestCase):
    def setUp(self):
        self.user = make_user('display-admin', 'Admin')
        self.node = make_node()
        self.vm = Instance.objects.create(
            name='display-vm',
            libvirt_domain_name='cv-display',
            node=self.node,
            image=make_image(node=self.node),
            created_by=self.user,
            vcpu=2,
            memory_mib=1024,
            disk_gib=10,
            observed_state='SHUTOFF',
            observed_state_is_stale=False,
            creation_config={'hardware': {'firmware': 'uefi'}},
        )
        self.client.force_login(self.user)
        self.url = f'/api/v1/admin/vms/{self.vm.pk}/display/'
        self.data = {'model': 'virtio', 'width': 1920, 'height': 1080}

    def post(self, data=None):
        return self.client.post(self.url, data or self.data, content_type='application/json')

    def test_task_saves_verified_configuration_without_claiming_guest_mode(self):
        response = self.post()
        self.assertEqual(response.status_code, 202, response.content)
        with patch('apps.nodes.client.AgentClient.domain_display', return_value=self.data):
            result = execute_instance_display(Task.objects.get())
        self.assertFalse(result['guest_mode_confirmed'])
        self.vm.refresh_from_db()
        self.assertEqual(self.vm.creation_config['hardware']['video_width'], 1920)
        self.assertEqual(self.vm.creation_config['hardware']['firmware'], 'uefi')
        self.assertEqual(self.vm.operation_status, 'SUCCEEDED')

    def test_running_and_stale_guests_cannot_enqueue(self):
        for values in [
            {'observed_state': 'RUNNING'},
            {'observed_state': 'SHUTOFF', 'observed_state_is_stale': True},
        ]:
            Instance.objects.filter(pk=self.vm.pk).update(**values)
            self.assertEqual(self.post().status_code, 409)
        self.assertFalse(Task.objects.exists())

    def test_invalid_sizes_and_unknown_fields_rejected(self):
        for values in [
            {'width': 0},
            {'height': 2161},
            {'model': 'cirrus'},
            {'command': 'xrandr'},
            {'width': 1920.5},
        ]:
            self.assertEqual(self.post({**self.data, **values}).status_code, 400)
        self.assertFalse(Task.objects.exists())

    def test_duplicate_submission_is_mutually_exclusive(self):
        self.assertEqual(self.post().status_code, 202)
        self.assertEqual(self.post().status_code, 409)
        self.assertEqual(Task.objects.count(), 1)

    def test_other_users_cannot_change_or_read_foreign_vm(self):
        user = make_user('display-operator', 'Operator')
        self.client.force_login(user)
        self.assertEqual(self.post().status_code, 403)
        self.url = f'/api/v1/operator/vms/{self.vm.pk}/display/'
        self.assertEqual(self.post().status_code, 404)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        Instance.objects.filter(pk=self.vm.pk).update(created_by=user)
        self.assertIn(self.post().status_code, (403, 404))

    def test_agent_failure_does_not_save_requested_mode(self):
        self.assertEqual(self.post().status_code, 202)
        with (
            patch(
                'apps.nodes.client.AgentClient.domain_display',
                side_effect=AppError(ErrorCode.CONFLICT, 'VM running'),
            ),
            self.assertRaises(AppError),
        ):
            execute_instance_display(Task.objects.get())
        self.vm.refresh_from_db()
        self.assertNotIn('video_width', self.vm.creation_config['hardware'])
        self.assertEqual(self.vm.operation_status, 'FAILED')

    def test_creation_hardware_requires_paired_dimensions_and_model(self):
        for values in [{'video_width': 1920}, {'video_width': 1920, 'video_height': 1080}]:
            self.assertFalse(HardwareSerializer(data=values).is_valid())
        self.assertTrue(
            HardwareSerializer(
                data={'video_model': 'virtio', 'video_width': 1920, 'video_height': 1080}
            ).is_valid()
        )
