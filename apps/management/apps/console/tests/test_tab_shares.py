"""WHIP publishers have user/session scope; anonymous grants only receive video."""

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.console.broadcast_reconcile import reconcile_one
from apps.console.models import MediaSession, TabShare
from apps.instances.tests.helpers import make_user
from common.errors import AppError, ErrorCode


@override_settings(CONSOLE_REQUIRE_TLS=False)
class TabShareTests(TestCase):
    def setUp(self):
        self.owner = make_user('tab-owner', 'Operator')
        self.other = make_user('tab-other', 'Operator')
        self.client.force_login(self.owner)
        self.request_id = uuid.uuid4()
        self.base = '/api/v1/console/tab-shares'

    def start(self):
        def signal(url, method, sdp=None):
            return 'v=0\r\n', url + '/resource', 201

        with patch('apps.console.tab_shares.media_request', side_effect=signal):
            response = self.client.post(
                self.base,
                {'sdp': 'v=0\r\n', 'request_id': str(self.request_id)},
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 201, response.content)
        return TabShare.objects.get(request_id=self.request_id), response.json()

    def path(self):
        return self.base + '/requests/' + str(self.request_id)

    def test_publisher_does_not_require_a_vm_or_server_workbench(self):
        share, data = self.start()
        self.assertEqual(share.broadcast.kind, 'tab')
        self.assertIsNone(share.broadcast.instance_id)
        self.assertIsNone(share.broadcast.workspace_id)
        self.assertNotIn('upstream_resource', data)
        self.assertFalse(MediaSession.objects.exists())

    def test_public_grant_cannot_renew_or_stop_publisher(self):
        share, data = self.start()
        identity, token = data['watch_path'].split('#')[1].split('.')
        viewer = Client()
        self.assertEqual(
            viewer.get(
                f'/api/v1/console/broadcasts/{identity}/watch', HTTP_X_STREAM_TOKEN=token
            ).status_code,
            200,
        )
        self.assertIn(viewer.post(self.path(), HTTP_X_STREAM_TOKEN=token).status_code, [401, 403])
        self.client.force_login(self.other)
        self.assertEqual(self.client.delete(self.path()).status_code, 404)

    def test_relogin_cannot_reuse_old_publisher_lease(self):
        self.start()
        self.client.logout()
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self.path()).status_code, 404)

    @patch('apps.console.tab_shares.media_request', return_value=('', '', 204))
    def test_stop_revokes_link_and_releases_whip(self, signal):
        share, data = self.start()
        self.assertEqual(self.client.delete(self.path()).status_code, 204)
        share.broadcast.refresh_from_db()
        self.assertFalse(share.broadcast.active)
        self.assertTrue(share.broadcast.stop_complete)
        self.assertEqual(share.broadcast.public_token_hash, '')
        signal.assert_called_once_with(share.upstream_resource, 'DELETE')

    @patch('apps.console.tab_shares.media_request', return_value=('', '', 204))
    def test_browser_crash_expires_and_background_worker_reaps(self, signal):
        share, _ = self.start()
        share.expires_at = timezone.now() - timedelta(seconds=1)
        share.save()
        reconcile_one(share.broadcast_id, reset_connections=False)
        share.broadcast.refresh_from_db()
        self.assertFalse(share.broadcast.active)
        self.assertTrue(share.broadcast.stop_complete)

    def test_failed_delete_stays_pending_for_retry(self):
        share, _ = self.start()
        with patch(
            'apps.console.tab_shares.media_request',
            side_effect=AppError(ErrorCode.OPERATION_FAILED),
        ):
            self.client.delete(self.path())
        share.broadcast.refresh_from_db()
        self.assertFalse(share.broadcast.active)
        self.assertFalse(share.broadcast.stop_complete)

    def test_logout_immediately_revokes_viewing(self):
        share, _ = self.start()
        self.assertEqual(self.client.post('/api/v1/auth/logout').status_code, 200)
        share.broadcast.refresh_from_db()
        self.assertFalse(share.broadcast.active)
        self.assertEqual(share.broadcast.public_token_hash, '')

    def test_invalid_offer_does_not_allocate_resources(self):
        self.assertEqual(
            self.client.post(
                self.base, {'sdp': 'invalid'}, content_type='application/json'
            ).status_code,
            400,
        )
        self.assertFalse(TabShare.objects.exists())

    @patch('apps.console.tab_shares.source_ready', return_value=True)
    def test_live_requires_gateway_observation(self, ready):
        share, _ = self.start()
        self.assertEqual(share.broadcast.state, 'STARTING')
        reconcile_one(share.broadcast_id, reset_connections=False)
        share.broadcast.refresh_from_db()
        self.assertEqual(share.broadcast.state, 'LIVE')
