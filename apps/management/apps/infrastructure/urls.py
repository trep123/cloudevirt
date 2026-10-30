from django.urls import path

from .storage_api import (
    StorageBackendDetailView,
    StorageBackendListView,
    StorageBackendProbeView,
    StorageDriversView,
)
from .views import (
    AvailableStoragePoolsView,
    OrganizationView,
    SettingsView,
    SnapshotsView,
    StoragePoolAccessView,
    StoragePoolsView,
)

urlpatterns = [
    path('admin/storage-drivers/', StorageDriversView.as_view()),
    path('admin/storage-backends/', StorageBackendListView.as_view()),
    path('admin/storage-backends/<int:pk>/', StorageBackendDetailView.as_view()),
    path('admin/storage-backends/<int:pk>/probe/', StorageBackendProbeView.as_view()),
    path('admin/clusters/', OrganizationView.as_view(), {'kind': 'clusters'}),
    path('admin/clusters/<int:pk>/', OrganizationView.as_view(), {'kind': 'clusters'}),
    path('admin/resource-pools/', OrganizationView.as_view(), {'kind': 'pools'}),
    path('admin/resource-pools/<int:pk>/', OrganizationView.as_view(), {'kind': 'pools'}),
    path('admin/settings/', SettingsView.as_view()),
    path('admin/nodes/<int:node_id>/storage-pools/', StoragePoolsView.as_view()),
    path(
        'admin/nodes/<int:node_id>/storage-pools/<str:name>/access/',
        StoragePoolAccessView.as_view(),
    ),
    path('storage-pools/available/', AvailableStoragePoolsView.as_view()),
    path('snapshots/instances/<int:instance_id>/', SnapshotsView.as_view()),
]
