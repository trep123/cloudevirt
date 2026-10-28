"""Viewer authorization interface. Link grants are intentionally independent of VM permissions."""

import hashlib
import secrets
from typing import Protocol

from django.utils import timezone

from common.errors import AppError, ErrorCode


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class ViewerPolicy(Protocol):
    def authorize(self, request, broadcast): ...
    def session_valid(self, session): ...


class LinkPolicy:
    def authorize(self, request, broadcast):
        token = request.headers.get('X-Stream-Token', '')
        if (
            not self.available(broadcast)
            or len(token) > 128
            or not secrets.compare_digest(digest(token), broadcast.public_token_hash)
        ):
            raise AppError(ErrorCode.PERMISSION_DENIED, '观看链接无效、已过期或已撤销')

    def available(self, broadcast):
        return (
            broadcast.active
            and broadcast.owner.is_active
            and broadcast.source.enabled
            and bool(broadcast.public_token_hash)
            and broadcast.link_expires_at
            and broadcast.link_expires_at > timezone.now()
        )

    def session_valid(self, session):
        return (
            self.available(session.broadcast)
            and session.access_version == session.broadcast.access_version
        )


def policy_for(broadcast):
    policies = {'link': LinkPolicy}
    implementation = policies.get(broadcast.access_mode)
    if not implementation:
        raise AppError(ErrorCode.PERMISSION_DENIED, '此观看授权方式暂不可用')
    return implementation()
