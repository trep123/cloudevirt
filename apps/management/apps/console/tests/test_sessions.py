"""Console authorization, single-use claims, source scopes and cleanup boundaries."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.console.media import safe_resource
from apps.console.models import ConsoleSession, MediaSession, MediaSource
from apps.console.services import gateway_key
from apps.instances.models import Instance
from apps.instances.tests.helpers import make_image, make_node, make_user
from common.errors import AppError


@override_settings(
    CONSOLE_REQUIRE_TLS=False, AGENT_SHARED_TOKEN='test-console-secret-that-is-long-enough'
)
class ConsoleTests(TestCase):
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

    def test_media_source_is_not_visible_to_other_users(self):
        source = MediaSource.objects.create(instance=self.vm, name='camera', stream_path='camera')
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(f'/api/v1/console/instances/{self.vm.pk}/media-sources').status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f'/api/v1/console/media-sources/{source.pk}/sessions',
                {'sdp': 'v=0\r\n'},
                content_type='application/json',
            ).status_code,
            404,
        )

    def test_ordinary_user_cannot_register_media(self):
        self.assertEqual(
            self.client.post(
                f'/api/v1/console/instances/{self.vm.pk}/media-sources',
                {'name': 'camera', 'stream_path': 'camera'},
                content_type='application/json',
            ).status_code,
            403,
        )

    @patch('apps.console.media.media_request')
    def test_media_uses_platform_identity_and_hides_upstream_location(self, request):
        source = MediaSource.objects.create(instance=self.vm, name='camera', stream_path='camera')
        request.return_value = ('v=0\r\n', '/camera/whep/resource-1', 201)
        response = self.client.post(
            f'/api/v1/console/media-sources/{source.pk}/sessions',
            {'sdp': 'v=0\r\n'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('upstream_resource', response.json())
        session = MediaSession.objects.get(pk=response.json()['session_id'])
        self.assertEqual(session.user, self.owner)
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.delete(f'/api/v1/console/media-sessions/{session.pk}').status_code, 404
        )

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

    @override_settings(
        MEDIA_TURN_URLS=['turn:relay.invalid:3478'],
        MEDIA_TURN_SECRET='server-only-secret',
        MEDIA_STUN_URLS=[],
    )
    def test_turn_credentials_are_temporary_and_do_not_expose_server_secret(self):
        import base64
        import hashlib
        import hmac

        from django.utils import timezone

        response = self.client.get(f'/api/v1/console/instances/{self.vm.pk}/media-sources')
        self.assertEqual(response.status_code, 200)
        server = response.json()['ice_servers'][0]
        expiry, owner = server['username'].split(':')
        self.assertEqual(int(owner), self.owner.pk)
        remaining = int(expiry) - int(timezone.now().timestamp())
        self.assertGreaterEqual(remaining, 599)
        self.assertLessEqual(remaining, 600)
        expected = base64.b64encode(
            hmac.new(b'server-only-secret', server['username'].encode(), hashlib.sha1).digest()
        ).decode()
        self.assertEqual(server['credential'], expected)
        self.assertNotIn('server-only-secret', response.content.decode())

    def test_media_location_is_not_an_ssrf_target(self):
        for location in [
            'http://attacker.invalid/private',
            '/different/api',
            '/camera/whep/../../admin',
        ]:
            with self.assertRaises(AppError):
                safe_resource('http://127.0.0.1:8889/camera/whep', location)
