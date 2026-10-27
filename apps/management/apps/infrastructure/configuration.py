"""Live configuration reads shared by API, quota checks and dashboards."""

from django.conf import settings

from .models import ConsoleConfiguration


def configuration():
    defaults = {
        'quota': dict(settings.USER_RESOURCE_QUOTA),
        'storage_warning_percent': 80,
        'storage_critical_percent': 90,
    }
    row = ConsoleConfiguration.objects.filter(pk=1).first()
    if row:
        defaults.update(row.values)
    return {'revision': row.revision if row else 0, **defaults}
