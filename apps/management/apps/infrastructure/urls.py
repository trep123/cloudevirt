from django.urls import path

from .views import OrganizationView, SettingsView, SnapshotsView, StoragePoolsView

urlpatterns = [
    path('admin/clusters/', OrganizationView.as_view(), {'kind': 'clusters'}),
    path('admin/clusters/<int:pk>/', OrganizationView.as_view(), {'kind': 'clusters'}),
    path('admin/resource-pools/', OrganizationView.as_view(), {'kind': 'pools'}),
    path('admin/resource-pools/<int:pk>/', OrganizationView.as_view(), {'kind': 'pools'}),
    path('admin/settings/', SettingsView.as_view()),
    path('admin/nodes/<int:node_id>/storage-pools/', StoragePoolsView.as_view()),
    path('snapshots/instances/<int:instance_id>/', SnapshotsView.as_view()),
]
