"""登录与密码策略服务。

登录失败提示统一，不泄露用户名是否存在；连续失败达到阈值锁定账号；
所有登录结果写入审计。
"""

import hashlib
import ipaddress
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import AbstractUser
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import LoginRateBucket, UserProfile
from apps.audit.models import AuditAction, AuditResult
from apps.audit.services import record_audit
from common.errors import AppError, ErrorCode

# 统一失败文案，避免通过提示差异探测账号是否存在
INVALID_CREDENTIALS_MESSAGE = '用户名或密码错误'


def client_ip(request) -> str | None:
    """提取并校验客户端 IP。

    Args:
        request: HTTP 请求。

    Returns:
        合法 IP 字符串；无法解析时返回 None。
    """
    raw = request.META.get('REMOTE_ADDR', '') if request else ''
    try:
        peer = ipaddress.ip_address(raw)
    except ValueError:
        return None
    if peer.is_loopback and getattr(settings, 'SECURE_PROXY_SSL_HEADER', None):
        forwarded = request.META.get('HTTP_X_REAL_IP', '')
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return str(peer)


def get_or_create_profile(user: AbstractUser) -> UserProfile:
    """获取用户档案，不存在时创建。

    Args:
        user: Django 用户。

    Returns:
        用户档案对象。
    """
    profile, _ = UserProfile.objects.get_or_create(
        user=user, defaults={'display_name': user.get_username()}
    )
    return profile


def enforce_login_rate_limit(request, username: str) -> None:
    """限制同一 IP + 账号的登录尝试频率。

    Args:
        request: HTTP 请求。
        username: 尝试登录的账号。

    Raises:
        AppError: 触发限流时抛出 RATE_LIMITED(429)。
    """
    ip = client_ip(request) or 'unknown'
    # Never store a probed username in a cache key or log.  The database is
    # shared by every Gunicorn process; row locking makes the count atomic.
    account_key = hashlib.sha256(f'account\0{ip}\0{username}'.encode()).hexdigest()
    ip_key = hashlib.sha256(f'ip\0{ip}'.encode()).hexdigest()
    window = getattr(settings, 'SECURITY_LOGIN_WINDOW_SECONDS', 300)
    account_limit = min(
        getattr(settings, 'SECURITY_LOGIN_MAX_ATTEMPTS', 10),
        getattr(settings, 'SECURITY_LOGIN_MAX_FAILED', 5),
    )
    ip_limit = getattr(settings, 'SECURITY_LOGIN_MAX_IP_ATTEMPTS', 50)
    now = timezone.now()
    limited = False
    with transaction.atomic():
        # Stable key ordering avoids deadlocks when attempts arrive concurrently.
        buckets = []
        for key, limit in sorted(((account_key, account_limit), (ip_key, ip_limit))):
            bucket, _ = LoginRateBucket.objects.get_or_create(
                key=key,
                defaults={'expires_at': now + timedelta(seconds=window)},
            )
            bucket = LoginRateBucket.objects.select_for_update().get(pk=bucket.pk)
            if bucket.expires_at <= now:
                bucket.attempts = 0
                bucket.expires_at = now + timedelta(seconds=window)
            limited = limited or bucket.attempts >= limit
            buckets.append(bucket)
        if not limited:
            for bucket in buckets:
                bucket.attempts += 1
                bucket.save(update_fields=['attempts', 'expires_at'])
    if limited:
        raise AppError(ErrorCode.RATE_LIMITED, '登录尝试过于频繁，请稍后再试')


def login_user(request, username: str, password: str) -> AbstractUser:
    """执行登录：限流、锁定检查、认证、审计。

    Args:
        request: HTTP 请求。
        username: 账号。
        password: 密码。

    Returns:
        认证成功的用户对象。

    Raises:
        AppError: 限流(429)、账号锁定或凭据错误(401)。
    """
    enforce_login_rate_limit(request, username)
    ip = client_ip(request)
    user_model = get_user_model()
    existing = user_model.objects.filter(username=username).first()

    if existing is not None:
        profile = get_or_create_profile(existing)
        if profile.is_locked:
            record_audit(
                action=AuditAction.LOGIN_FAILURE,
                actor=existing,
                target_type='user',
                target_id=username,
                result=AuditResult.FAILURE,
                details={'reason': 'locked'},
                ip=ip,
            )
            raise AppError(ErrorCode.UNAUTHORIZED, INVALID_CREDENTIALS_MESSAGE)

    user = authenticate(request, username=username, password=password)
    if user is None:
        if existing is not None:
            profile = get_or_create_profile(existing)
            profile.register_failure(
                getattr(settings, 'SECURITY_LOGIN_MAX_FAILED', 5),
                getattr(settings, 'SECURITY_LOGIN_LOCK_SECONDS', 900),
            )
        record_audit(
            action=AuditAction.LOGIN_FAILURE,
            actor=existing,
            actor_username=username,
            target_type='user',
            target_id=username,
            result=AuditResult.FAILURE,
            details={'reason': 'invalid_credentials'},
            ip=ip,
        )
        raise AppError(ErrorCode.UNAUTHORIZED, INVALID_CREDENTIALS_MESSAGE)

    if not user.is_active:
        record_audit(
            action=AuditAction.LOGIN_FAILURE,
            actor=user,
            target_type='user',
            target_id=username,
            result=AuditResult.FAILURE,
            details={'reason': 'disabled'},
            ip=ip,
        )
        raise AppError(ErrorCode.UNAUTHORIZED, INVALID_CREDENTIALS_MESSAGE)

    profile = get_or_create_profile(user)
    profile.register_success(ip)
    record_audit(
        action=AuditAction.LOGIN_SUCCESS,
        actor=user,
        target_type='user',
        target_id=username,
        result=AuditResult.SUCCESS,
        ip=ip,
    )
    return user


def validate_password_policy(password: str) -> None:
    """校验密码长度策略。

    Args:
        password: 待校验的明文密码。

    Raises:
        AppError: 长度不足时抛出 VALIDATION_ERROR(400)。
    """
    min_length = getattr(settings, 'SECURITY_PASSWORD_MIN_LENGTH', 12)
    if len(password) < min_length:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            '密码长度不足',
            details={'password': [f'密码长度不能少于 {min_length} 位']},
        )


def change_password(user: AbstractUser, new_password: str) -> None:
    """修改密码并更新档案标记。

    Args:
        user: 目标用户。
        new_password: 新密码明文。
    """
    validate_password_policy(new_password)
    user.set_password(new_password)
    user.save(update_fields=['password'])
    profile = get_or_create_profile(user)
    profile.must_change_password = False
    profile.password_changed_at = timezone.now()
    profile.save(update_fields=['must_change_password', 'password_changed_at', 'updated_at'])
    record_audit(
        action=AuditAction.PASSWORD_CHANGE,
        actor=user,
        target_type='user',
        target_id=str(user.pk),
    )
