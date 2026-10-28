"""One-use tickets share the existing authenticated VNC transport."""

import base64
import hashlib
import hmac
import json
from datetime import timedelta
from types import SimpleNamespace

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response

from common.errors import AppError, ErrorCode

from .models import WorkspaceControlSession
from .services import agent_target
from .workspaces import endpoint, owned_control


def authorize_workspace(request, pk):
    get_object_or_404(WorkspaceControlSession.objects.select_for_update(), pk=pk, user=request.user)
    session = owned_control(request, pk)
    if session.claimed or session.revoked or session.expires_at <= timezone.now():
        raise AppError(ErrorCode.PERMISSION_DENIED, '控制票据已使用或过期')
    target, host = agent_target(SimpleNamespace(node=SimpleNamespace(endpoint=endpoint())))
    payload = {
        'sid': str(session.pk),
        'workspace': str(session.workspace_id),
        'generation': str(session.generation),
        'exp': int(timezone.now().timestamp()) + 30,
    }
    encoded = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode())
        .decode()
        .rstrip('=')
    )
    signature = hmac.new(
        settings.AGENT_SHARED_TOKEN.encode(), ('console-v1.' + encoded).encode(), hashlib.sha256
    ).hexdigest()
    session.claimed = True
    session.expires_at = timezone.now() + timedelta(seconds=90)
    session.save(update_fields=['claimed', 'expires_at'])
    response = Response(status=204)
    response['X-Console-Target'] = target
    response['X-Console-Node-Host'] = host
    response['X-Console-Ticket'] = encoded + '.' + signature
    response['Cache-Control'] = 'no-store'
    return response
