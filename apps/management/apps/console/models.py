"""Authenticated per-instance desktop console leases."""

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
