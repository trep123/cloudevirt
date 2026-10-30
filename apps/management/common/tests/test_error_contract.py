"""统一错误结构契约测试。"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import path

from common.views import health


@override_settings(ROOT_URLCONF='common.tests.urls')
class ErrorContractTests(TestCase):
    """验证所有错误路径都返回统一结构。"""

    def test_app_error_returns_mapped_status_and_body(self) -> None:
        """业务异常应映射为对应状态码与统一响应体。"""
        response = self.client.get('/test/app-error')

        self.assertEqual(response.status_code, 409)
        body = response.json()['error']
        self.assertEqual(body['code'], 'INSUFFICIENT_RESOURCE')
        self.assertEqual(body['details'], {'resource': 'memory_mib'})
        self.assertTrue(body['request_id'])
        self.assertEqual(set(body), {'code', 'message', 'details', 'request_id'})

    def test_validation_error_returns_field_details(self) -> None:
        """校验错误应返回 400 与字段级明细。"""
        response = self.client.get('/test/validation-error')

        self.assertEqual(response.status_code, 400)
        body = response.json()['error']
        self.assertEqual(body['code'], 'VALIDATION_ERROR')
        self.assertEqual(body['details'], {'memory_mib': ['必须大于 0']})

    def test_not_found_returns_404(self) -> None:
        """资源不存在应返回 404 NOT_FOUND。"""
        response = self.client.get('/test/not-found')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error']['code'], 'NOT_FOUND')

    def test_unexpected_error_does_not_leak_details(self) -> None:
        """未捕获异常应返回通用文案，不得泄露内部信息。"""
        response = self.client.get('/test/unexpected')

        self.assertEqual(response.status_code, 500)
        body = response.json()['error']
        self.assertEqual(body['code'], 'INTERNAL_ERROR')
        self.assertNotIn('internal-secret-should-not-leak', response.content.decode())
        self.assertNotIn('Traceback', response.content.decode())

    def test_unauthenticated_returns_401(self) -> None:
        """未认证访问受保护接口应返回 401 UNAUTHORIZED。"""
        response = self.client.get('/test/auth-required')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error']['code'], 'UNAUTHORIZED')

    def test_authenticated_user_without_permission_returns_403(self) -> None:
        """已认证但无权限应返回 403 PERMISSION_DENIED。"""
        user_model = get_user_model()
        user_model.objects.create_user(username='viewer01', password='pwd-only-for-test')
        self.client.login(username='viewer01', password='pwd-only-for-test')

        response = self.client.get('/test/admin-only')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error']['code'], 'PERMISSION_DENIED')

    def test_authenticated_user_can_access(self) -> None:
        """已认证用户访问普通接口应成功。"""
        user_model = get_user_model()
        user_model.objects.create_user(username='operator01', password='pwd-only-for-test')
        self.client.login(username='operator01', password='pwd-only-for-test')

        response = self.client.get('/test/auth-required')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True})


# 健康检查位于 config.urls，这里在模块级声明同名路由以便独立测试
urlpatterns = [path('api/v1/health', health)]


class JsonErrorPageTests(TestCase):
    """未匹配路由的错误页也应返回 JSON（使用默认 config.urls）。"""

    def test_unmatched_route_returns_json_404(self) -> None:
        """访问不存在的 API 路径应返回 JSON 结构的 404。"""
        response = self.client.get('/api/v1/does-not-exist')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error']['code'], 'NOT_FOUND')


@override_settings(ROOT_URLCONF='common.tests.test_error_contract')
class HealthViewTests(TestCase):
    """健康检查契约测试。"""

    def test_health_returns_ok_without_authentication(self) -> None:
        """健康检查免认证，但不披露版本号。"""
        response = self.client.get('/api/v1/health')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')
        self.assertNotIn('version', response.json())
