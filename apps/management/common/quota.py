"""Configurable ordinary-user resource ceilings."""

from django.db.models import Sum

from apps.accounts.roles import is_admin
from apps.instances.models import Instance
from common.errors import AppError, ErrorCode


def quota_for(user):
    from apps.infrastructure.configuration import configuration

    queryset = Instance.objects.filter(created_by=user, is_deleted=False)
    usage = queryset.aggregate(
        vcpu=Sum('vcpu'), memory_mib=Sum('memory_mib'), disk_gib=Sum('disk_gib')
    )
    return {
        'enforced': not is_admin(user),
        'limits': {
            **configuration()['quota'],
            **getattr(getattr(user, 'profile', None), 'quota_overrides', {}),
        },
        'used': {
            'instances': queryset.count(),
            **{key: value or 0 for key, value in usage.items()},
        },
    }


def enforce_quota(user, *, vcpu, memory_mib, disk_gib):
    quota = quota_for(user)
    if not quota['enforced']:
        return
    requested = {'instances': 1, 'vcpu': vcpu, 'memory_mib': memory_mib, 'disk_gib': disk_gib}
    shortages = [
        key for key, value in requested.items() if quota['used'][key] + value > quota['limits'][key]
    ]
    if shortages:
        raise AppError(
            ErrorCode.INSUFFICIENT_RESOURCE,
            '账号资源配额不足',
            details={
                'quota': quota,
                'exceeded': shortages,
            },
        )
