from unittest.mock import patch

from django.test import TestCase

from apps.instances.tests.helpers import make_node, make_user
from apps.networks.bridges import execute_bridge
from apps.networks.models import Network
from apps.networks.services import validate_network_for_instance
from apps.tasks.models import Task
from common.errors import AppError


class BridgeTests(TestCase):
    def setUp(self):
        self.admin = make_user('bridge-admin', 'Admin')
        self.user = make_user('bridge-user', 'Viewer')
        self.node = make_node()
        self.client.force_login(self.admin)
        self.payload = {
            'name': 'data-net',
            'node': self.node.pk,
            'type': 'BRIDGE',
            'bridge': 'br-data',
            'uplink': 'eth1',
        }

    def post(self, payload=None, key='bridge-request'):
        return self.client.post(
            '/api/v1/networks/bridges',
            payload or self.payload,
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=key,
        )

    @patch('apps.networks.bridges.AgentClient')
    def test_enqueue_and_idempotent_replay(self, client):
        client.return_value.get_json.return_value = {
            'interfaces': [{'name': 'eth1', 'eligible': True}]
        }
        first = self.post()
        self.assertEqual(first.status_code, 202, first.content)
        self.assertEqual(self.post().json()['task_id'], first.json()['task_id'])
        self.assertEqual(Task.objects.count(), 1)
        self.assertFalse(Network.objects.get().is_usable)
        self.assertEqual(self.post({**self.payload, 'bridge': 'br-other'}).status_code, 409)

    @patch('apps.networks.bridges.AgentClient')
    def test_unsafe_physical_nic_never_enqueued(self, client):
        client.return_value.get_json.return_value = {
            'interfaces': [{'name': 'eth1', 'eligible': False, 'reason': 'management'}]
        }
        self.assertEqual(self.post().status_code, 409)
        self.assertFalse(Task.objects.exists())
        self.assertFalse(Network.objects.exists())

    @patch('apps.networks.bridges.AgentClient')
    def test_viewer_cannot_provision_even_with_network_permission(self, client):
        from django.contrib.auth.models import Permission

        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label='networks', codename='manage_network')
        )
        self.client.force_login(self.user)
        self.assertEqual(self.post().status_code, 403)
        client.assert_not_called()

    @patch('apps.networks.bridges.AgentClient')
    def test_ready_only_after_matching_agent_ack(self, client):
        client.return_value.get_json.return_value = {
            'interfaces': [{'name': 'eth1', 'eligible': True}]
        }
        self.post()
        task = Task.objects.get()
        client.return_value.request_json.return_value = {
            'verified': True,
            'type': 'BRIDGE',
            'bridge': 'br-other',
            'uplink': 'eth1',
        }
        with self.assertRaises(AppError):
            execute_bridge(task)
        self.assertFalse(Network.objects.get().is_usable)
        client.return_value.request_json.return_value = {
            'verified': True,
            'type': 'BRIDGE',
            'bridge': 'br-data',
            'uplink': 'eth1',
        }
        execute_bridge(task)
        self.assertTrue(Network.objects.get().is_usable)

    def test_node_scope_and_incomplete_bridge_are_enforced(self):
        other = make_node(name='other-node')
        n = Network.objects.create(
            name='scoped', type='BRIDGE', bridge='br-data', node=self.node, managed=True
        )
        with self.assertRaises(AppError):
            validate_network_for_instance(n.name, other)
        self.assertEqual(validate_network_for_instance(n.name, self.node), n)
        n.provisioning_status = 'PENDING'
        n.save()
        with self.assertRaises(AppError):
            validate_network_for_instance(n.name, self.node)

    @patch('apps.networks.bridges.AgentClient')
    def test_revoked_admin_cannot_execute_queued_bridge(self, client):
        client.return_value.get_json.return_value = {
            'interfaces': [{'name': 'eth1', 'eligible': True}]
        }
        self.post()
        task = Task.objects.get()
        self.admin.groups.clear()
        with self.assertRaises(AppError):
            execute_bridge(task)
        client.return_value.request_json.assert_not_called()
