"""Explicit administrator and ordinary-user authorization boundaries."""

from django.urls import path

from apps.accounts.roles import is_admin
from apps.instances.views import (
    InstanceActionView,
    InstanceAddressesView,
    InstanceConsoleView,
    InstanceDetailView,
    InstanceInterfacesView,
    InstanceListCreateView,
)
from apps.tasks.views import TaskCancelView, TaskDetailView, TaskListView, TaskRetryView
from common.console import AuditListView, DashboardView, QuotaView
from common.errors import AppError, ErrorCode


class ConsoleBoundaryMixin:
    admin_scope = False

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if is_admin(request.user) != self.admin_scope:
            raise AppError(ErrorCode.PERMISSION_DENIED, '账号不属于此控制台的授权范围')


ROUTES = [
    ('dashboard/', DashboardView),
    ('vms/', InstanceListCreateView),
    ('vms/<int:pk>/', InstanceDetailView),
    ('vms/<int:pk>/addresses/', InstanceAddressesView),
    ('vms/<int:pk>/interfaces/', InstanceInterfacesView),
    ('vms/<int:pk>/console/', InstanceConsoleView),
    ('vms/<int:pk>/<str:action>/', InstanceActionView),
    ('tasks/', TaskListView),
    ('tasks/<uuid:pk>/', TaskDetailView),
    ('tasks/<uuid:pk>/cancel/', TaskCancelView),
    ('tasks/<uuid:pk>/retry/', TaskRetryView),
    ('audit/', AuditListView),
    ('quota/', QuotaView),
]

urlpatterns = []
for namespace, admin_scope in [('admin', True), ('operator', False)]:
    for route, base in ROUTES:
        view = type(
            f'{namespace.title()}{base.__name__}',
            (ConsoleBoundaryMixin, base),
            {'admin_scope': admin_scope, '__module__': __name__},
        )
        urlpatterns.append(path(f'{namespace}/{route}', view.as_view()))
