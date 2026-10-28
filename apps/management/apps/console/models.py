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
    instance = models.ForeignKey('instances.Instance', on_delete=models.PROTECT)
    name = models.CharField(max_length=64)
    stream_path = models.CharField(max_length=64)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class MediaSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    source = models.ForeignKey(MediaSource, on_delete=models.PROTECT)
    login_hash = models.CharField(max_length=64)
    upstream_resource = models.CharField(max_length=1024, blank=True, default='')
    closed = models.BooleanField(default=False)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.pk)
