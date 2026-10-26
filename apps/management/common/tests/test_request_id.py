"""request_id 链路追踪测试。"""

from django.test import TestCase, override_settings


@override_settings(ROOT_URLCONF='common.tests.urls')
class RequestIDTests(TestCase):
    """验证 request_id 生成、透传与响应头回写。"""

    def test_valid_inbound_request_id_is_reused(self) -> None:
        """调用方传入的合法 request_id 应被复用，便于跨系统追踪。"""
        response = self.client.get(
            '/test/app-error', headers={'X-Request-ID': 'trace-abcdef-123456'}
        )

        self.assertEqual(response.headers['X-Request-ID'], 'trace-abcdef-123456')
        self.assertEqual(response.json()['error']['request_id'], 'trace-abcdef-123456')

    def test_invalid_inbound_request_id_is_replaced(self) -> None:
        """非法 request_id 应被丢弃并重新生成，避免回显任意输入。"""
        response = self.client.get('/test/app-error', headers={'X-Request-ID': 'bad id!!'})

        generated = response.headers['X-Request-ID']
        self.assertNotEqual(generated, 'bad id!!')
        self.assertEqual(len(generated), 32)
        self.assertEqual(response.json()['error']['request_id'], generated)
