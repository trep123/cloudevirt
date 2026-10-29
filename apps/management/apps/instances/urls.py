"""实例路由。"""

from django.urls import path

from apps.instances.preflight import CreatePreflightView
from apps.instances.display import InstanceDisplayView
from apps.instances.device_management import InstanceHardwareView
from apps.instances.views import (
    DiskListView,
    InstanceActionView,
    InstanceAddressesView,
    InstanceConsoleView,
    InstanceDetailView,
    InstanceInterfacesView,
    InstanceListCreateView,
)

urlpatterns = [
    path('instances/<int:pk>/hardware', InstanceHardwareView.as_view()),
    path('instances/<int:pk>/display', InstanceDisplayView.as_view()),
    path('instances/preflight', CreatePreflightView.as_view()),
    path('instances', InstanceListCreateView.as_view(), name='instance-list'),
    path(
        'instances/<int:pk>/addresses', InstanceAddressesView.as_view(), name='instance-addresses'
    ),
    path(
        'instances/<int:pk>/interfaces',
        InstanceInterfacesView.as_view(),
        name='instance-interfaces',
    ),
    path(
        'instances/<int:pk>/console',
        InstanceConsoleView.as_view(),
        name='instance-console',
    ),
    # 动作路由必须在详情路由之前，避免 "start" 等被当作 pk
    path('instances/<int:pk>/<str:action>', InstanceActionView.as_view(), name='instance-action'),
    path('instances/<int:pk>', InstanceDetailView.as_view(), name='instance-detail'),
    path('disks', DiskListView.as_view(), name='disk-list'),
]
