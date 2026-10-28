"""Publishing is server owned; public capabilities grant video viewing only."""

from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.console.broadcast_reconcile import reconcile_one
from apps.console.models import Broadcast, MediaSession, MediaSource
from apps.instances.models import Instance
from apps.instances.tests.helpers import make_image, make_node, make_user


@override_settings(CONSOLE_REQUIRE_TLS=False, MEDIA_STUN_URLS=[], MEDIA_TURN_URLS=[])
class BroadcastTests(TestCase):
    def setUp(self):
        self.owner = make_user('stream-owner', 'Operator')
        self.other = make_user('stream-other', 'Operator')
        self.vm = Instance.objects.create(
            name='stream-vm',
            libvirt_domain_name='stream-test',
            node=make_node(),
            image=make_image(),
            created_by=self.owner,
            vcpu=1,
            memory_mib=512,
            disk_gib=5,
            vnc_password='private-pass',
            observed_state='RUNNING',
        )
        self.client.force_login(self.owner)
        self.viewer = Client(enforce_csrf_checks=True)

    def start(self, kind='desktop', source=None):
        payload = {'kind': kind}
        if source:
            payload['source_id'] = source.pk
        response = self.client.post(
            f'/api/v1/console/instances/{self.vm.pk}/broadcasts',
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 202)
        data = response.json()
        identity, token = data['watch_path'].split('#')[1].split('.')
        return Broadcast.objects.get(pk=identity), token

    def watch(self, broadcast, token):
        return self.viewer.get(
            f'/api/v1/console/broadcasts/{broadcast.pk}/watch', HTTP_X_STREAM_TOKEN=token
        )

    def offer(self, broadcast, token):
        return self.viewer.post(
            f'/api/v1/console/broadcasts/{broadcast.pk}/watch',
            {'sdp': 'v=0\r\n'},
            content_type='application/json',
            HTTP_X_STREAM_TOKEN=token,
        )

    def source(self):
        return MediaSource.objects.create(instance=self.vm, name='camera', stream_path='camera')

    def test_open_does_not_create_a_viewer_and_link_secret_is_not_stored(self):
        broadcast, token = self.start()
        self.assertEqual(broadcast.state, 'QUEUED')
        self.assertFalse(MediaSession.objects.exists())
        self.assertNotIn(token, broadcast.public_token_hash)
        self.assertTrue(broadcast.source.is_desktop)
        response = self.client.get(f'/api/v1/console/instances/{self.vm.pk}/broadcasts')
        self.assertNotIn(token, response.content.decode())
        self.assertNotIn('watch_path', response.json()['results'][0])

    def test_only_resource_owner_can_publish(self):
        self.client.force_login(self.other)
        response = self.client.post(
            f'/api/v1/console/instances/{self.vm.pk}/broadcasts',
            {'kind': 'desktop'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)

    def test_public_link_does_not_require_login_or_grant_vm_api_access(self):
        broadcast, token = self.start()
        self.assertEqual(self.watch(broadcast, token).status_code, 200)
        self.assertEqual(self.watch(broadcast, 'invalid').status_code, 403)
        self.assertIn(self.viewer.get(f'/api/v1/instances/{self.vm.pk}').status_code, [401, 403])
        self.assertIn(self.viewer.get('/api/v1/nodes').status_code, [401, 403])
        self.assertNotIn('sessionid', self.viewer.cookies)

    @patch(
        'apps.console.broadcast_views.media_request',
        return_value=('v=0\r\n', '/camera/whep/session-1', 201),
    )
    def test_source_can_be_requested_on_demand_with_scoped_viewer_lease(self, upstream):
        broadcast, token = self.start('source', self.source())
        response = self.offer(broadcast, token)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        session = MediaSession.objects.get(pk=data['session_id'])
        self.assertIsNone(session.user)
        self.assertNotEqual(session.viewer_token_hash, data['lease_token'])
        url = f'/api/v1/console/watch-sessions/{session.pk}'
        self.assertEqual(self.viewer.post(url, HTTP_X_MEDIA_SESSION_TOKEN='wrong').status_code, 403)
        self.assertEqual(
            self.viewer.post(url, HTTP_X_MEDIA_SESSION_TOKEN=data['lease_token']).status_code, 200
        )
        self.assertFalse('upstream_resource' in data)

    @patch('apps.console.media.media_request', return_value=('', '', 204))
    @patch(
        'apps.console.broadcast_views.media_request',
        return_value=('v=0\r\n', '/camera/whep/session-1', 201),
    )
    def test_rotating_link_revokes_existing_viewers(self, offer, delete):
        broadcast, token = self.start('source', self.source())
        data = self.offer(broadcast, token).json()
        rotated = self.client.post(
            f'/api/v1/console/broadcasts/{broadcast.pk}', {}, content_type='application/json'
        )
        self.assertEqual(rotated.status_code, 200)
        self.assertEqual(self.watch(broadcast, token).status_code, 403)
        call_command('cleanup_console_sessions')
        self.assertTrue(MediaSession.objects.get(pk=data['session_id']).closed)
        delete.assert_called_once()

    def test_expiry_and_stop_invalidate_links(self):
        broadcast, token = self.start()
        broadcast.link_expires_at = timezone.now() - timedelta(seconds=1)
        broadcast.save(update_fields=['link_expires_at'])
        self.assertEqual(self.watch(broadcast, token).status_code, 403)
        self.client.delete(f'/api/v1/console/broadcasts/{broadcast.pk}')
        self.assertEqual(self.watch(broadcast, token).status_code, 403)

    @override_settings(BROADCAST_MAX_VIEWERS=1)
    @patch(
        'apps.console.broadcast_views.media_request',
        return_value=('v=0\r\n', '/camera/whep/session-1', 201),
    )
    def test_viewer_capacity_is_enforced_before_opening_an_upstream_session(self, upstream):
        broadcast, token = self.start('source', self.source())
        self.assertEqual(self.offer(broadcast, token).status_code, 201)
        self.assertEqual(self.offer(broadcast, token).status_code, 429)
        upstream.assert_called_once()

    @patch('apps.console.broadcast_reconcile.source_ready', return_value=True)
    @patch('apps.console.broadcast_reconcile.AgentClient')
    def test_server_reconciliation_starts_and_renews_capture_without_a_browser(self, agent, ready):
        agent.return_value.request_json.side_effect = lambda path, method, data: {
            'status': 'STOPPED' if method == 'DELETE' else 'RUNNING'
        }
        broadcast, token = self.start()
        reconcile_one(broadcast.pk, reset_connections=False)
        broadcast.refresh_from_db()
        self.assertEqual(broadcast.state, 'LIVE')
        self.assertFalse(MediaSession.objects.exists())
        self.assertEqual(agent.return_value.request_json.call_args.args[1], 'POST')
        self.client.delete(f'/api/v1/console/broadcasts/{broadcast.pk}')
        reconcile_one(broadcast.pk, reset_connections=False)
        broadcast.refresh_from_db()
        self.assertEqual(broadcast.state, 'STOPPED')
        self.assertTrue(broadcast.stop_complete)
        self.assertEqual(agent.return_value.request_json.call_args.args[1], 'DELETE')
