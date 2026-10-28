"""Desktop and media leases with shared authorization and independent recovery."""

import uuid

from django.conf import settings
from django.db import models


class ConsoleSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    instance = models.ForeignKey('instances.Instance', on_delete=models.PROTECT)
    login_hash = models.CharField(max_length=64)
    claimed = models.BooleanField(default=False)
    revoked = models.BooleanField(default=False)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.pk)


class MediaSource(models.Model):
    instance = models.ForeignKey(
        'instances.Instance', on_delete=models.PROTECT, null=True, blank=True
    )
    name = models.CharField(max_length=64)
    stream_path = models.CharField(max_length=64)
    enabled = models.BooleanField(default=True)
    is_desktop = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class MediaSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True
    )
    broadcast = models.ForeignKey(
        'console.Broadcast', on_delete=models.PROTECT, null=True, blank=True
    )
    access_version = models.UUIDField(null=True, blank=True)
    viewer_token_hash = models.CharField(max_length=64, blank=True, default='')
    source = models.ForeignKey(MediaSource, on_delete=models.PROTECT)
    login_hash = models.CharField(max_length=64)
    upstream_resource = models.CharField(max_length=1024, blank=True, default='')
    closed = models.BooleanField(default=False)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.pk)


class Broadcast(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instance = models.ForeignKey(
        'instances.Instance', on_delete=models.PROTECT, null=True, blank=True
    )
    workspace = models.OneToOneField(
        'console.UserWorkspace',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='broadcast',
    )
    source = models.OneToOneField(MediaSource, on_delete=models.PROTECT)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(
        max_length=16, choices=[('desktop', '桌面'), ('source', '视频源'), ('page', '用户工作台')]
    )
    active = models.BooleanField(default=False)
    stop_complete = models.BooleanField(default=True)
    state = models.CharField(max_length=16, default='STOPPED')
    error = models.CharField(max_length=256, blank=True, default='')
    publish_id = models.UUIDField(default=uuid.uuid4)
    access_mode = models.CharField(max_length=16, default='link')
    access_version = models.UUIDField(default=uuid.uuid4)
    public_token_hash = models.CharField(max_length=64, blank=True, default='')
    link_expires_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    live_since = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['instance'],
                condition=models.Q(kind='desktop'),
                name='uniq_desktop_broadcast_per_vm',
            ),
            models.CheckConstraint(
                condition=models.Q(kind='page', workspace__isnull=False, instance__isnull=True)
                | models.Q(
                    kind__in=['desktop', 'source'], workspace__isnull=True, instance__isnull=False
                ),
                name='broadcast_scope_matches_kind',
            ),
        ]

    def __str__(self):
        return str(self.pk)


class UserWorkspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    generation = models.UUIDField(default=uuid.uuid4)
    active = models.BooleanField(default=False)
    stop_complete = models.BooleanField(default=True)
    state = models.CharField(max_length=16, default='STOPPED')
    error = models.CharField(max_length=256, blank=True, default='')
    initial_path = models.CharField(max_length=512, default='/app/vms')
    expires_at = models.DateTimeField(null=True, blank=True)
    owner_auth_hash = models.CharField(max_length=64, blank=True, default='')
    bootstrap_hash = models.CharField(max_length=64, blank=True, default='')
    bootstrap_expires_at = models.DateTimeField(null=True, blank=True)
    browser_session_key = models.CharField(max_length=40, blank=True, default='')
    vnc_password = models.CharField(max_length=8, blank=True, default='')
    attempts = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = [('use_workspace', '可以使用持久共享工作台')]

    def __str__(self):
        return str(self.pk)


class WorkspaceControlSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(UserWorkspace, on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    generation = models.UUIDField()
    login_hash = models.CharField(max_length=64)
    claimed = models.BooleanField(default=False)
    revoked = models.BooleanField(default=False)
    expires_at = models.DateTimeField(db_index=True)

    def __str__(self):
        return str(self.pk)
