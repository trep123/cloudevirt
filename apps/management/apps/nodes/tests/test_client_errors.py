"""The actual public Agent message survives transport without exposing raw responses."""

import io
import json
from unittest import mock
from urllib.error import HTTPError

from django.test import SimpleTestCase

from apps.nodes.client import AgentClient
from common.errors import AppError


class AgentErrorTests(SimpleTestCase):
    def test_missing_image_retains_actionable_message(self):
        error = HTTPError(
            'http://agent/api',
            404,
            'missing',
            {},
            io.BytesIO(
                json.dumps(
                    {
                        'code': 'NOT_FOUND',
                        'message': '节点镜像目录中找不到文件',
                        'request_id': 'agent-request-id',
                    }
                ).encode()
            ),
        )
        with mock.patch('urllib.request.urlopen', side_effect=error):
            with self.assertRaises(AppError) as context:
                AgentClient('http://agent').inspect_image('rocky10.qcow2')
        self.assertEqual(context.exception.code, 'NOT_FOUND')
        self.assertIn('找不到文件', context.exception.message)
        self.assertEqual(context.exception.details['agent_request_id'], 'agent-request-id')

    def test_agent_auth_failure_does_not_expire_browser_session(self):
        error = HTTPError(
            'http://agent/api',
            401,
            'token mismatch',
            {},
            io.BytesIO(b'{"code":"UNAUTHORIZED","message":"token"}'),
        )
        with mock.patch('urllib.request.urlopen', side_effect=error):
            with self.assertRaises(AppError) as context:
                AgentClient('http://agent').health()
        self.assertEqual(context.exception.code, 'OPERATION_FAILED')
        self.assertNotEqual(context.exception.status_code, 401)
        self.assertIn('共享令牌', context.exception.message)

    def test_proxy_html_is_not_exposed(self):
        error = HTTPError(
            'http://agent/api',
            502,
            'bad gateway',
            {},
            io.BytesIO(b'<html>private internal host</html>'),
        )
        with mock.patch('urllib.request.urlopen', side_effect=error):
            with self.assertRaises(AppError) as context:
                AgentClient('http://agent').health()
        self.assertNotIn('private internal host', str(context.exception))
