"""登录、登出与密码策略测试。"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.accounts.models import UserProfile
from apps.accounts.services import client_ip
from apps.audit.models import AuditAction, AuditEvent, AuditResult


@override_settings(SECURITY_PASSWORD_MIN_LENGTH=8)
class LoginTests(TestCase):
    """登录相关用例。"""

    def setUp(self) -> None:
        """创建测试用户。"""
        self.user = get_user_model().objects.create_user(
            username='alice', password='Str0ngPassw0rd'
        )
        UserProfile.objects.create(user=self.user, display_name='爱丽丝')

    def test_login_success_writes_audit(self) -> None:
        """登录成功应返回用户信息并写入成功审计。"""
        response = self.client.post(
            '/api/v1/auth/login', {'username': 'alice', 'password': 'Str0ngPassw0rd'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['username'], 'alice')
        event = AuditEvent.objects.filter(action=AuditAction.LOGIN_SUCCESS).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.actor_id, self.user.pk)
        self.assertEqual(event.result, AuditResult.SUCCESS)
        self.assertIsNotNone(event.created_at)
        self.assertEqual(event.target_type, 'user')

    def test_login_wrong_password_returns_401_with_uniform_message(self) -> None:
        """密码错误应返回 401，且提示不区分账号是否存在。"""
        response = self.client.post(
            '/api/v1/auth/login', {'username': 'alice', 'password': 'wrong-password'}
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error']['code'], 'UNAUTHORIZED')
        self.assertEqual(response.json()['error']['message'], '用户名或密码错误')
        event = AuditEvent.objects.filter(action=AuditAction.LOGIN_FAILURE).first()
        self.assertEqual(event.result, AuditResult.FAILURE)

    def test_login_unknown_user_returns_same_message(self) -> None:
        """不存在的账号应返回相同提示，避免账号枚举。"""
        response = self.client.post(
            '/api/v1/auth/login', {'username': 'ghost', 'password': 'whatever-password'}
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error']['message'], '用户名或密码错误')

    @override_settings(SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
    def test_proxy_ip_only_trusted_for_loopback_peer(self) -> None:
        """仅允许本机 nginx 覆写来源 IP，阻止客户端伪造限流键。"""
        from django.test import RequestFactory

        factory = RequestFactory()
        local = factory.get('/', REMOTE_ADDR='127.0.0.1', HTTP_X_REAL_IP='192.0.2.12')
        remote = factory.get('/', REMOTE_ADDR='192.0.2.15', HTTP_X_REAL_IP='192.0.2.12')
        self.assertEqual(client_ip(local), '192.0.2.12')
        self.assertEqual(client_ip(remote), '192.0.2.15')

    @override_settings(SECURITY_LOGIN_MAX_FAILED=2, SECURITY_LOGIN_LOCK_SECONDS=600)
    def test_account_is_locked_after_repeated_failures(self) -> None:
        """连续失败达到阈值后账号应被锁定。"""
        for _ in range(2):
            self.client.post(
                '/api/v1/auth/login', {'username': 'alice', 'password': 'bad-password'}
            )
        response = self.client.post(
            '/api/v1/auth/login', {'username': 'alice', 'password': 'Str0ngPassw0rd'}
        )

        self.assertEqual(response.status_code, 429)
        self.assertTrue(UserProfile.objects.get(user=self.user).is_locked)

    @override_settings(SECURITY_LOGIN_MAX_FAILED=2, SECURITY_LOGIN_MAX_ATTEMPTS=10)
    def test_unknown_and_existing_accounts_have_same_lock_response(self) -> None:
        """未知用户与已锁定用户不能靠响应码和文案区分。"""
        results = []
        for username in ('alice', 'ghost'):
            attempts = [
                self.client.post('/api/v1/auth/login', {'username': username, 'password': 'wrong'})
                for _ in range(3)
            ]
            results.append(
                [(item.status_code, item.json()['error']['message']) for item in attempts]
            )
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][-1][0], 429)

    @override_settings(SECURITY_LOGIN_MAX_IP_ATTEMPTS=2)
    def test_ip_limit_blocks_username_spray(self) -> None:
        """切换用户名不能绕过来源地址的总尝试次数限制。"""
        responses = [
            self.client.post('/api/v1/auth/login', {'username': f'unknown-{i}', 'password': 'bad'})
            for i in range(3)
        ]
        self.assertEqual([response.status_code for response in responses], [401, 401, 429])

    def test_disabled_user_cannot_login(self) -> None:
        """已停用用户不能登录。"""
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])

        response = self.client.post(
            '/api/v1/auth/login', {'username': 'alice', 'password': 'Str0ngPassw0rd'}
        )

        self.assertEqual(response.status_code, 401)

    @override_settings(SECURITY_LOGIN_MAX_ATTEMPTS=2, SECURITY_LOGIN_WINDOW_SECONDS=300)
    def test_login_rate_limit_returns_429(self) -> None:
        """短时间多次尝试应触发限流。"""
        for _ in range(2):
            self.client.post(
                '/api/v1/auth/login', {'username': 'alice', 'password': 'bad-password'}
            )
        response = self.client.post(
            '/api/v1/auth/login', {'username': 'alice', 'password': 'bad-password'}
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()['error']['code'], 'RATE_LIMITED')

    def test_me_requires_authentication(self) -> None:
        """未认证访问当前用户信息应返回 401。"""
        self.assertEqual(self.client.get('/api/v1/auth/me').status_code, 401)

    def test_me_returns_roles_and_permissions(self) -> None:
        """认证后应返回角色与权限清单。"""
        self.client.login(username='alice', password='Str0ngPassw0rd')

        response = self.client.get('/api/v1/auth/me')

        self.assertEqual(response.status_code, 200)
        self.assertIn('roles', response.json())
        self.assertIn('permissions', response.json())

    def test_logout_invalidates_session(self) -> None:
        """登出后会话失效。"""
        self.client.login(username='alice', password='Str0ngPassw0rd')
        self.assertEqual(self.client.post('/api/v1/auth/logout').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/auth/me').status_code, 401)

    def test_csrf_cookie_is_issued_and_login_requires_token(self) -> None:
        """开启 CSRF 校验时，前端需先取令牌再提交写操作。"""
        client = Client(enforce_csrf_checks=True)

        probe = client.get('/api/v1/auth/me')
        self.assertEqual(probe.status_code, 401)
        self.assertIn('csrftoken', client.cookies)
        token = client.cookies['csrftoken'].value

        response = client.post(
            '/api/v1/auth/login',
            {'username': 'alice', 'password': 'Str0ngPassw0rd'},
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, 200)

    def test_change_password_rejects_weak_password(self) -> None:
        """弱密码应被拒绝。"""
        self.client.login(username='alice', password='Str0ngPassw0rd')

        response = self.client.post(
            '/api/v1/auth/change-password',
            {'old_password': 'Str0ngPassw0rd', 'new_password': '123'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'VALIDATION_ERROR')

    def test_change_password_success(self) -> None:
        """正确修改密码后标记应被清除。"""
        self.client.login(username='alice', password='Str0ngPassw0rd')

        response = self.client.post(
            '/api/v1/auth/change-password',
            {'old_password': 'Str0ngPassw0rd', 'new_password': 'An0therStr0ngPass'},
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('An0therStr0ngPass'))
