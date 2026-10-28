"""账户 API：登录、登出、当前用户、用户与角色管理。"""

import secrets
import string

from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.administration import (
    invalidate_user,
    protect_administrator,
    serialize_admin_changes,
)
from apps.accounts.models import UserProfile
from apps.accounts.serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from apps.accounts.services import change_password, login_user
from apps.audit.models import AuditAction
from apps.audit.services import record_audit
from common.errors import AppError, ErrorCode
from common.permissions import CanManageUser, RequiresPasswordChange


def generate_temporary_password(length: int = 16) -> str:
    """生成一次性随机口令。

    Args:
        length: 口令长度，默认 16。

    Returns:
        随机口令字符串。
    """
    alphabet = string.ascii_letters + string.digits
    characters = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
    ] + [secrets.choice(alphabet) for _ in range(max(13, length - 3))]
    secrets.SystemRandom().shuffle(characters)
    return ''.join(characters)


@method_decorator(ensure_csrf_cookie, name='dispatch')
class LoginView(APIView):
    """登录接口，免认证。"""

    permission_classes = [AllowAny]

    def post(self, request) -> Response:
        """认证并建立会话，同时写审计（响应下发 CSRF Cookie）。"""
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = login_user(
            request,
            serializer.validated_data['username'],
            serializer.validated_data['password'],
        )
        login(request, user)
        request.session['_auth_epoch'] = getattr(
            getattr(user, 'profile', None), 'session_version', 0
        )
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    """登出接口。"""

    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        """销毁会话并写审计。"""
        record_audit(
            action=AuditAction.LOGOUT,
            actor=request.user,
            target_type='user',
            target_id=str(request.user.pk),
        )
        from apps.console.models import ConsoleSession
        from apps.console.services import login_hash

        identity = login_hash(request)
        ConsoleSession.objects.filter(user=request.user, login_hash=identity, revoked=False).update(
            expires_at=timezone.now()
        )
        logout(request)
        return Response({'ok': True})


@method_decorator(ensure_csrf_cookie, name='dispatch')
class MeView(APIView):
    """当前登录用户信息。"""

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        """返回用户、角色与权限清单（同时下发 CSRF Cookie 供前端取用）。"""
        data = UserSerializer(request.user).data
        data['permissions'] = sorted(request.user.get_all_permissions())
        return Response(data)


class ChangePasswordView(APIView):
    """修改当前用户密码。"""

    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        """校验旧密码后设置新密码。"""
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data['old_password']):
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                '旧密码不正确',
                details={'old_password': ['旧密码不正确']},
            )
        change_password(request.user, serializer.validated_data['new_password'])
        # 保持当前会话有效，避免改密后被立即登出
        update_session_auth_hash(request, request.user)
        return Response({'ok': True})


class UserListCreateView(generics.ListCreateAPIView):
    """用户列表与创建（仅管理员）。"""

    permission_classes = [CanManageUser, RequiresPasswordChange]
    queryset = get_user_model().objects.all().order_by('id')

    def get_queryset(self):
        query = super().get_queryset().select_related('profile').prefetch_related('groups')
        search = self.request.query_params.get('search', '').strip()
        if search:
            query = query.filter(
                Q(username__icontains=search)
                | Q(profile__display_name__icontains=search)
                | Q(email__icontains=search)
            )
        role = self.request.query_params.get('role')
        if role:
            query = query.filter(groups__name=role)
        active = self.request.query_params.get('active')
        if active in {'true', 'false'}:
            query = query.filter(is_active=active == 'true')
        return query.distinct()

    def get_serializer_class(self):
        """写操作使用创建序列化器。"""
        if self.request.method == 'POST':
            return UserCreateSerializer
        return UserSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs) -> Response:
        """创建用户并以输出序列化器回显真实角色。"""
        serialize_admin_changes()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = self.perform_create(serializer)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        """保存用户并写审计，返回新建用户。"""
        user = serializer.save()
        record_audit(
            action=AuditAction.USER_CREATE,
            actor=self.request.user,
            target_type='user',
            target_id=str(user.pk),
            details={'username': user.get_username(), 'roles': UserSerializer(user).data['roles']},
        )
        return user


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """用户详情、更新与停用（仅管理员）。

    DELETE 语义为停用（保留审计链），不做物理删除。
    """

    permission_classes = [CanManageUser, RequiresPasswordChange]
    queryset = get_user_model().objects.all()

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        serialize_admin_changes()
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=kwargs.pop('partial', False)
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(UserSerializer(serializer.instance).data)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        serialize_admin_changes()
        return super().destroy(request, *args, **kwargs)

    def get_serializer_class(self):
        """写操作使用更新序列化器。"""
        if self.request.method == 'GET':
            return UserSerializer
        return UserUpdateSerializer

    def perform_update(self, serializer) -> None:
        """保存变更并按启用/停用分别审计。"""
        before_active = serializer.instance.is_active
        before_roles = sorted(serializer.instance.groups.values_list('name', flat=True))
        user = serializer.save()
        if before_active != user.is_active:
            action = AuditAction.USER_ENABLE if user.is_active else AuditAction.USER_DISABLE
        else:
            action = AuditAction.USER_UPDATE
        record_audit(
            action=action,
            actor=self.request.user,
            target_type='user',
            target_id=str(user.pk),
            details={
                'username': user.get_username(),
                'is_active': user.is_active,
                'before_roles': before_roles,
                'roles': sorted(user.groups.values_list('name', flat=True)),
                'node_scope': getattr(getattr(user, 'profile', None), 'node_scope', None),
                'quota_overrides': getattr(getattr(user, 'profile', None), 'quota_overrides', {}),
            },
        )

    def perform_destroy(self, instance) -> None:
        """停用用户而不是物理删除。"""
        protect_administrator(instance, active=False)
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        invalidate_user(instance)
        record_audit(
            action=AuditAction.USER_DISABLE,
            actor=self.request.user,
            target_type='user',
            target_id=str(instance.pk),
            details={'username': instance.get_username(), 'is_active': False},
        )


class UserResetPasswordView(APIView):
    """管理员重置用户密码（仅管理员）。"""

    permission_classes = [CanManageUser, RequiresPasswordChange]

    def post(self, request, pk: int) -> Response:
        """生成一次性口令并强制用户下次登录改密。"""
        user = get_user_model().objects.filter(pk=pk).first()
        if user is None:
            raise AppError(ErrorCode.NOT_FOUND)
        password = generate_temporary_password()
        user.set_password(password)
        user.save(update_fields=['password'])
        profile, _ = UserProfile.objects.get_or_create(
            user=user, defaults={'display_name': user.get_username()}
        )
        profile.must_change_password = True
        profile.password_changed_at = timezone.now()
        profile.save(update_fields=['must_change_password', 'password_changed_at', 'updated_at'])
        record_audit(
            action=AuditAction.USER_PASSWORD_RESET,
            actor=request.user,
            target_type='user',
            target_id=str(user.pk),
            details={'username': user.get_username()},
        )
        invalidate_user(user)
        response = Response({'username': user.get_username(), 'password': password})
        response['Cache-Control'] = 'no-store'
        return response


class UserAuditView(APIView):
    """用户最近审计事件，用于详情页展示操作历史。"""

    permission_classes = [CanManageUser, RequiresPasswordChange]

    def get(self, request, pk: int) -> Response:
        """返回该用户最近 50 条审计事件。"""
        from apps.audit.models import AuditEvent

        events = list(
            AuditEvent.objects.filter(actor_id=pk)
            .order_by('-created_at')[:50]
            .values('id', 'action', 'target_type', 'target_id', 'details', 'created_at')
        )
        return Response({'results': events})
