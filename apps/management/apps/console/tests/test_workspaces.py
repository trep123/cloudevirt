"""Workspace ownership, token scope, persistence and revocation boundaries."""

import secrets
from datetime import timedelta
from unittest.mock import patch

from django.contrib.sessions.models import Session
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.console.broadcast_access import digest
from apps.console.management.commands.reconcile_workspaces import reconcile_workspace
from apps.console.models import MediaSession, UserWorkspace
from apps.console.services import gateway_key
from apps.instances.tests.helpers import make_user


@override_settings(CONSOLE_REQUIRE_TLS=False, WORKBENCH_ENABLED=True)
class WorkspaceTests(TestCase):
    def setUp(self):
        self.owner = make_user('workspace-owner', 'Operator')
        self.other = make_user('workspace-other', 'Operator')
        self.client.force_login(self.owner)
        self.base = '/api/v1/console/workspaces/my'

    def start(self):
        result = self.client.post(self.base, {}, content_type='application/json')
        self.assertEqual(result.status_code, 202, result.content)
        return UserWorkspace.objects.get(owner=self.owner), result.json()

    def test_user_scoped_source_no_vm_and_no_self_playback(self):
        workspace, data = self.start()
        self.assertIsNone(workspace.broadcast.instance_id)
        self.assertIsNone(workspace.broadcast.source.instance_id)
        self.assertEqual(workspace.broadcast.kind, 'page')
        self.assertFalse(MediaSession.objects.exists())
        self.assertNotIn('vnc_password', data)
        self.assertNotIn('owner_auth_hash', data)
        repeated = self.client.post(self.base, {}, content_type='application/json')
        self.assertNotIn('watch_path', repeated.json())
        self.assertEqual(UserWorkspace.objects.count(), 1)

    def test_another_user_cannot_control_but_can_view_with_link(self):
        workspace, data = self.start()
        self.client.force_login(self.other)
        result = self.client.post(f'/api/v1/console/workspaces/{workspace.pk}/sessions')
        self.assertEqual(result.status_code, 404)
        identity, token = data['watch_path'].split('#')[1].split('.')
        viewer = Client()
        response = viewer.get(
            f'/api/v1/console/broadcasts/{identity}/watch', HTTP_X_STREAM_TOKEN=token
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(viewer.get(self.base).status_code, [401, 403])
        self.assertNotIn('sessionid', viewer.cookies)

    def test_bootstrap_is_one_use_and_uses_dedicated_session(self):
        workspace, _ = self.start()
        token = secrets.token_urlsafe(32)
        workspace.bootstrap_hash = digest(token)
        workspace.bootstrap_expires_at = timezone.now() + timedelta(seconds=120)
        workspace.save()
        browser = Client(enforce_csrf_checks=True)
        path = f'/api/v1/console/workspaces/{workspace.pk}/bootstrap'
        result = browser.post(path, HTTP_X_WORKSPACE_BOOTSTRAP=token)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(browser.get('/api/v1/auth/me').json()['workbench_id'], str(workspace.pk))
        self.assertNotEqual(browser.session.session_key, self.client.session.session_key)
        self.assertEqual(browser.post(path, HTTP_X_WORKSPACE_BOOTSTRAP=token).status_code, 403)
        workspace.refresh_from_db()
        self.assertEqual(workspace.bootstrap_hash, '')
        self.assertEqual(workspace.browser_session_key, browser.session.session_key)

    @patch('apps.console.management.commands.reconcile_workspaces.client')
    def test_local_logout_does_not_stop_server_browser(self, agent):
        workspace, _ = self.start()
        agent.return_value.get_json.return_value = {
            'state': 'READY',
            'generation': str(workspace.generation),
        }
        self.client.logout()
        reconcile_workspace(workspace.pk)
        workspace.refresh_from_db()
        self.assertTrue(workspace.active)
        self.assertEqual(workspace.state, 'READY')

    @patch('apps.console.management.commands.reconcile_workspaces.client')
    def test_expiry_revokes_links_and_reaps_runtime(self, agent):
        workspace, _ = self.start()
        workspace.expires_at = timezone.now() - timedelta(seconds=1)
        workspace.save()
        agent.return_value.request_json.return_value = {'state': 'STOPPED'}
        reconcile_workspace(workspace.pk)
        workspace.refresh_from_db()
        workspace.broadcast.refresh_from_db()
        self.assertFalse(workspace.active)
        self.assertTrue(workspace.stop_complete)
        self.assertEqual(workspace.vnc_password, '')
        self.assertFalse(workspace.broadcast.active)

    def test_stop_deletes_only_dedicated_browser_session(self):
        workspace, _ = self.start()
        dedicated = Client()
        dedicated.force_login(self.owner)
        workspace.browser_session_key = dedicated.session.session_key
        workspace.save()
        self.assertEqual(self.client.delete(self.base).status_code, 202)
        self.assertFalse(Session.objects.filter(session_key=dedicated.session.session_key).exists())
        self.assertTrue(
            Session.objects.filter(session_key=self.client.session.session_key).exists()
        )

    def test_no_recursive_workspaces_or_open_redirect(self):
        response = self.client.post(
            self.base, {'initial_path': '//evil.example/'}, content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        session = self.client.session
        session['workbench_id'] = 'server-session'
        session.save()
        self.assertEqual(self.client.post(self.base).status_code, 409)

    def test_owner_control_ticket_is_one_use_and_bound_to_login(self):
        workspace, _ = self.start()
        workspace.state = 'READY'
        workspace.save()
        response = self.client.post(f'/api/v1/console/workspaces/{workspace.pk}/sessions')
        self.assertEqual(response.status_code, 201)
        path = response.json()['path']
        headers = {
            'HTTP_ORIGIN': 'http://testserver',
            'HTTP_X_ORIGINAL_URI': path,
            'HTTP_X_CONSOLE_GATEWAY_KEY': gateway_key(),
        }
        authorized = self.client.get('/api/v1/console/authorize', **headers)
        self.assertEqual(authorized.status_code, 204)
        self.assertEqual(self.client.get('/api/v1/console/authorize', **headers).status_code, 403)
        self.client.logout()
        self.assertIn(
            self.client.get('/api/v1/console/authorize', **headers).status_code, [401, 403]
        )

    @patch('apps.console.management.commands.reconcile_workspaces.client')
    def test_password_change_invalidates_persistent_workspace(self, agent):
        workspace, _ = self.start()
        self.owner.set_password('a-different-password')
        self.owner.save()
        agent.return_value.request_json.return_value = {'state': 'STOPPED'}
        reconcile_workspace(workspace.pk)
        workspace.refresh_from_db()
        self.assertFalse(workspace.active)
        self.assertTrue(workspace.stop_complete)
