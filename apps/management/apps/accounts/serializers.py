"""账户相关序列化器。

原则：只接受业务字段，不接受客户端提交的 is_superuser / is_staff 等提权字段。
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.accounts.administration import (
    invalidate_user,
    protect_administrator,
    validate_quota,
    validate_scope,
    validated_roles,
)
from apps.accounts.models import UserProfile
from apps.accounts.roles import is_admin
from apps.accounts.services import validate_password_policy
from common.errors import AppError


class AdministrativeInput:
    def to_internal_value(self, data):
        unknown = set(data) - {name for name, field in self.fields.items() if not field.read_only}
        if unknown:
            raise serializers.ValidationError(
                {name: ['不允许导入或修改此字段'] for name in sorted(unknown)}
            )
        return super().to_internal_value(data)

    def validate_roles(self, value):
        return validated_roles(value)

    def validate_quota_overrides(self, value):
        return validate_quota(value)

    def validate_node_scope(self, value):
        return validate_scope(value)


class LoginSerializer(serializers.Serializer):
    """登录请求。"""

    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, max_length=256)


class ChangePasswordSerializer(serializers.Serializer):
    """修改密码请求。"""

    old_password = serializers.CharField(write_only=True, max_length=256)
    new_password = serializers.CharField(write_only=True, max_length=256)

    def validate_new_password(self, value: str) -> str:
        """校验新密码长度与复杂度。"""
        validate_password_policy(value)
        validate_password(value)
        return value


class UserSerializer(serializers.ModelSerializer):
    """用户输出结构。"""

    display_name = serializers.CharField(source='profile.display_name', read_only=True)
    must_change_password = serializers.BooleanField(
        source='profile.must_change_password', read_only=True
    )
    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    console_scope = serializers.SerializerMethodField()
    remark = serializers.CharField(source='profile.remark', read_only=True, default='')
    quota_overrides = serializers.JSONField(
        source='profile.quota_overrides', read_only=True, default=dict
    )
    node_scope = serializers.JSONField(source='profile.node_scope', read_only=True, allow_null=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = (
            'id',
            'username',
            'display_name',
            'email',
            'is_active',
            'roles',
            'permissions',
            'console_scope',
            'must_change_password',
            'last_login',
            'date_joined',
            'remark',
            'quota_overrides',
            'node_scope',
            'status',
        )
        read_only_fields = ('last_login', 'date_joined')

    def get_roles(self, obj) -> list[str]:
        """返回用户角色名列表。"""
        return sorted(obj.groups.values_list('name', flat=True))

    def get_status(self, obj):
        return (
            'pending'
            if not obj.has_usable_password()
            else 'active'
            if obj.is_active
            else 'disabled'
        )

    def get_permissions(self, obj) -> list[str]:
        """返回用户经角色继承的全部权限码（按字母序）。"""
        return sorted(obj.get_all_permissions())

    def get_console_scope(self, obj) -> str:
        return 'admin' if is_admin(obj) else 'user'


class UserCreateSerializer(AdministrativeInput, serializers.ModelSerializer):
    """管理员创建用户。"""

    display_name = serializers.CharField(max_length=64, required=False, allow_blank=True)
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=256
    )
    roles = serializers.ListField(
        child=serializers.CharField(max_length=150), required=False, default=lambda: ['Viewer']
    )
    remark = serializers.CharField(max_length=500, required=False, allow_blank=True)
    quota_overrides = serializers.JSONField(required=False)
    node_scope = serializers.JSONField(required=False, allow_null=True)

    class Meta:
        model = get_user_model()
        fields = (
            'id',
            'username',
            'email',
            'is_active',
            'display_name',
            'password',
            'roles',
            'remark',
            'quota_overrides',
            'node_scope',
        )
        read_only_fields = ('id',)

    def validate_username(self, value: str) -> str:
        """校验用户名长度与重复性。"""
        if len(value) < 3:
            raise serializers.ValidationError('用户名至少 3 个字符')
        if get_user_model().objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('用户名已存在')
        return value

    def validate(self, attrs):
        if attrs.get('password'):
            validate_password_policy(attrs['password'])
            validate_password(
                attrs['password'],
                get_user_model()(username=attrs.get('username', ''), email=attrs.get('email', '')),
            )
        return attrs

    def create(self, validated_data: dict):
        """创建用户、档案与角色绑定。"""
        display_name = validated_data.pop('display_name', '') or validated_data['username']
        password = validated_data.pop('password', '') or None
        roles = validated_data.pop('roles', []) or []
        roles = validated_roles(roles or ['Viewer'])
        extra = {
            name: validated_data.pop(name)
            for name in ['remark', 'quota_overrides', 'node_scope']
            if name in validated_data
        }
        user = get_user_model()(**validated_data)
        if password:
            validate_password_policy(password)
            user.set_password(password)
        else:
            user.set_unusable_password()
            user.is_active = False
        user.save()
        UserProfile.objects.create(
            user=user,
            display_name=display_name,
            must_change_password=not password,
            **extra,
        )
        if roles:
            from django.contrib.auth.models import Group

            user.groups.set(Group.objects.filter(name__in=roles))
        return user


class UserUpdateSerializer(AdministrativeInput, serializers.ModelSerializer):
    """管理员更新用户（不含密码）。"""

    display_name = serializers.CharField(max_length=64, required=False)
    roles = serializers.ListField(child=serializers.CharField(max_length=150), required=False)
    remark = serializers.CharField(max_length=500, required=False, allow_blank=True)
    quota_overrides = serializers.JSONField(required=False)
    node_scope = serializers.JSONField(required=False, allow_null=True)

    class Meta:
        model = get_user_model()
        fields = (
            'id',
            'username',
            'email',
            'is_active',
            'display_name',
            'roles',
            'remark',
            'quota_overrides',
            'node_scope',
        )
        read_only_fields = ('id', 'username')

    def validate(self, attrs):
        protect_administrator(
            self.instance, active=attrs.get('is_active'), roles=attrs.get('roles')
        )
        if attrs.get('is_active') and not self.instance.has_usable_password():
            raise serializers.ValidationError({'is_active': ['请先重置密码，再启用账号']})
        return attrs

    def update(self, instance, validated_data: dict):
        """更新用户基本字段与角色。"""
        from django.contrib.auth.models import Group

        display_name = validated_data.pop('display_name', None)
        roles = validated_data.pop('roles', None)
        extra = {
            name: validated_data.pop(name)
            for name in ['remark', 'quota_overrides', 'node_scope']
            if name in validated_data
        }
        revoke = roles is not None or 'is_active' in validated_data or 'node_scope' in extra
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if display_name is not None or extra:
            profile, _ = UserProfile.objects.get_or_create(
                user=instance, defaults={'display_name': display_name or instance.username}
            )
            if display_name is not None:
                profile.display_name = display_name
            for key, value in extra.items():
                setattr(profile, key, value)
            profile.save()
        if roles is not None:
            instance.groups.set(Group.objects.filter(name__in=roles))
        if revoke:
            invalidate_user(instance)
        return instance


def app_error_to_serializer(error: AppError) -> None:
    """把业务异常转换为序列化器校验错误，便于统一返回 400。"""
    raise serializers.ValidationError(error.details or {'detail': error.message})
