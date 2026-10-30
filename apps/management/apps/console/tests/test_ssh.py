import base64
import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.console.models import ConsoleSession
from apps.console.services import gateway_key
from apps.instances.models import Instance
from apps.instances.tests.helpers import make_image, make_node, make_user


@override_settings(
    CONSOLE_REQUIRE_TLS=False, AGENT_SHARED_TOKEN='test-console-secret-that-is-long-enough'
)
class WebSSHTests(TestCase):
    def setUp(self):
        self.owner = make_user('ssh-owner', 'Viewer')
        self.other = make_user('ssh-other', 'Viewer')
        self.node = make_node(resource_is_stale=False)
        self.vm = Instance.objects.create(
            name='ssh-vm',
            libvirt_domain_name='cv-ssh-vm',
            node=self.node,
            image=make_image(),
            created_by=self.owner,
            vcpu=1,
            memory_mib=512,
            disk_gib=5,
            observed_state='RUNNING',
            observed_state_is_stale=False,
        )
        self.path = f'/api/v1/console/instances/{self.vm.pk}/ssh'
        self.client.force_login(self.owner)
        self.agent = patch(
            'apps.nodes.client.AgentClient.get_json', return_value={'addresses': ['192.168.150.9']}
        ).start()
        self.addCleanup(patch.stopall)

    def create(self, body=None):
        return self.client.post(
            self.path, body or {'address': '192.168.150.9'}, content_type='application/json'
        )

    def test_owner_session_is_bound_to_address_and_gateway_only(self):
        self.assertEqual(self.client.get(self.path).json()['addresses'], ['192.168.150.9'])
        result = self.create()
        self.assertEqual(result.status_code, 201, result.content)
        self.assertNotIn('ticket', result.json())
        row = ConsoleSession.objects.get()
        self.assertEqual(row.protocol, 'ssh')
        self.assertEqual(row.ssh_address, '192.168.150.9')
        response = self.client.get(
            '/api/v1/console/authorize',
            HTTP_ORIGIN='http://testserver',
            HTTP_X_ORIGINAL_URI=result.json()['path'],
            HTTP_X_CONSOLE_GATEWAY_KEY=gateway_key(),
        )
        self.assertEqual(response.status_code, 204, response.content)
        self.assertTrue(response['X-Console-Target'].endswith('/ssh'))
        encoded = response['X-Console-Ticket'].split('.')[0]
        payload = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
        self.assertEqual(payload['protocol'], 'ssh')
        self.assertEqual(payload['address'], '192.168.150.9')
        with patch('apps.nodes.client.AgentClient.request_json', return_value={'active': True}):
            lease = f'/api/v1/console/sessions/{row.pk}'
            self.assertEqual(self.client.post(lease).status_code, 200)
            self.assertEqual(self.client.delete(lease).status_code, 204)

    def test_other_users_cannot_read_targets_create_or_reuse_session(self):
        result = self.create().json()
        self.client.force_login(self.other)
        self.agent.reset_mock()
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.assertEqual(self.create().status_code, 404)
        self.assertEqual(
            self.client.post(f'/api/v1/console/sessions/{result["session_id"]}').status_code, 404
        )
        self.agent.assert_not_called()

    def test_arbitrary_targets_and_rest_credentials_are_rejected(self):
        for body in [
            {'address': '127.0.0.1'},
            {'address': '192.168.150.9', 'password': 'do-not-store'},
            {'address': '192.168.150.9', 'port': 2222},
        ]:
            self.assertIn(self.create(body).status_code, [400, 403])
        self.assertFalse(ConsoleSession.objects.exists())

    def test_permission_and_running_state_are_required(self):
        self.vm.observed_state = 'SHUTOFF'
        self.vm.save()
        self.assertEqual(self.create().status_code, 409)
        self.vm.observed_state = 'RUNNING'
        self.vm.save()
        self.owner.groups.clear()
        self.assertEqual(self.create().status_code, 403)

    @override_settings(CONSOLE_REQUIRE_TLS=True)
    def test_insecure_transport_denied(self):
        self.assertEqual(self.client.get(self.path).status_code, 403)

    def test_remote_plaintext_agent_is_rejected_before_session_creation(self):
        self.node.endpoint = 'http://192.0.2.10:9100'
        self.node.save()
        self.assertEqual(self.create().status_code, 409)
        self.assertFalse(ConsoleSession.objects.exists())
