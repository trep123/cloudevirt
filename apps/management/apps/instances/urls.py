"""实例路由。"""

from django.urls import path

from apps.instances.views import InstanceDetailView, InstanceListCreateView

urlpatterns = [
    path('instances', InstanceListCreateView.as_view(), name='instance-list'),
    path('instances/<int:pk>', InstanceDetailView.as_view(), name='instance-detail'),
]
