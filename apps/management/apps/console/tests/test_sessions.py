"""Console authorization, single-use claims, source scopes and cleanup boundaries."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.console.models import ConsoleSession
from apps.console.services import gateway_key
from apps.instances.models import Instance
from apps.instances.tests.helpers import make_image, make_node, make_user


@override_settings(
    CONSOLE_REQUIRE_TLS=False, AGENT_SHARED_TOKEN='test-console-secret-that-is-long-enough'
)
class ConsoleTests(TestCase):
    def test_uuid_lease_renews_and_close_frees_quota(self):
        session = self.create()
        self.assertEqual(self.authorize(session).status_code, 204)
        path = f'/api/v1/console/sessions/{session["session_id"]}'
        with patch('apps.nodes.client.AgentClient.request_json', return_value={'active': True}):
            self.assertEqual(self.client.post(path).status_code, 200)
            for _ in range(2):
                self.create()
            self.assertEqual(self.client.delete(path).status_code, 204)
            self.assertEqual(self.client.delete(path).status_code, 204)
        self.assertTrue(ConsoleSession.objects.get(pk=session['session_id']).revoked)
        self.create()

    def test_lease_and_close_do_not_accept_other_login_or_user(self):
        session = self.create()
        path = f'/api/v1/console/sessions/{session["session_id"]}'
        self.client.force_login(self.other)
        with patch('apps.nodes.client.AgentClient.request_json') as agent:
            self.assertEqual(self.client.post(path).status_code, 404)
            self.assertEqual(self.client.delete(path).status_code, 404)
            agent.assert_not_called()

    def test_unclaimed_and_revoked_sessions_cannot_renew(self):
        session = self.create()
        path = f'/api/v1/console/sessions/{session["session_id"]}'
        self.assertEqual(self.client.post(path).status_code, 409)
        ConsoleSession.objects.filter(pk=session['session_id']).update(revoked=True)
        self.assertEqual(self.client.post(path).status_code, 409)

    def setUp(self):
        self.owner = make_user('console-test-owner', 'Operator')
        self.other = make_user('console-test-other', 'Operator')
        self.node = make_node()
        self.vm = Instance.objects.create(
            name='test-desktop',
            libvirt_domain_name='cv-console-test',
            node=self.node,
            image=make_image(),
            created_by=self.owner,
            vcpu=1,
            memory_mib=512,
            disk_gib=5,
            vnc_password='testpass',
            observed_state='RUNNING',
        )
        self.client.force_login(self.owner)

    def create(self):
        response = self.client.post(f'/api/v1/console/instances/{self.vm.pk}/sessions')
        self.assertEqual(response.status_code, 201)
        return response.json()

    def authorize(self, session, origin='http://testserver', key=None):
        return self.client.get(
            '/api/v1/console/authorize',
            HTTP_ORIGIN=origin,
            HTTP_X_ORIGINAL_URI=session['path'],
            HTTP_X_CONSOLE_GATEWAY_KEY=gateway_key() if key is None else key,
        )

    def test_ticket_is_internal_and_single_use(self):
        session = self.create()
        self.assertNotIn('sig=', session['path'])
        self.assertNotIn('X-Console-Ticket', session)
        self.assertEqual(self.authorize(session, key='').status_code, 403)
        response = self.authorize(session)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response['X-Console-Target'], 'http://127.0.0.1:9100/vnc')
        self.assertTrue(response['X-Console-Ticket'])
        self.assertEqual(self.authorize(session).status_code, 403)

    def test_origin_and_ownership(self):
        session = self.create()
        self.assertEqual(
            self.authorize(session, origin='https://attacker.invalid').status_code, 403
        )
        self.client.force_login(self.other)
        self.assertEqual(self.authorize(session).status_code, 404)
        self.assertEqual(
            self.client.post(f'/api/v1/console/instances/{self.vm.pk}/sessions').status_code, 404
        )

    def test_logout_invalidates_leases(self):
        session = self.create()
        self.client.post('/api/v1/auth/logout')
        from django.utils import timezone

        self.assertLessEqual(
            ConsoleSession.objects.get(pk=session['session_id']).expires_at, timezone.now()
        )

    def test_session_limit(self):
        for _ in range(3):
            self.create()
        self.assertEqual(
            self.client.post(f'/api/v1/console/instances/{self.vm.pk}/sessions').status_code, 409
        )

    def test_removed_publishing_and_viewer_routes_return_not_found(self):
        for path in [
            '/api/v1/console/tab-shares',
            '/api/v1/console/workspaces/my',
            f'/api/v1/console/instances/{self.vm.pk}/broadcasts',
            f'/api/v1/console/instances/{self.vm.pk}/media-sources',
            '/api/v1/console/broadcasts/00000000-0000-4000-8000-000000000001/watch',
        ]:
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_gateway_uses_the_registered_instance_node(self):
        self.vm.node = make_node(name='second-node', endpoint='http://127.0.0.2:9201')
        self.vm.save(update_fields=['node'])
        response = self.authorize(self.create())
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response['X-Console-Target'], 'http://127.0.0.2:9201/vnc')

    @override_settings(CONSOLE_REQUIRE_TLS=True)
    def test_plain_http_cannot_create_a_desktop_session(self):
        response = self.client.post(f'/api/v1/console/instances/{self.vm.pk}/sessions')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ConsoleSession.objects.exists())
