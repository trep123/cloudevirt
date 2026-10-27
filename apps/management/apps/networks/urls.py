"""网络路由。"""

from django.urls import path

from apps.networks.views import NetworkDetailView, NetworkListCreateView

urlpatterns = [
    path('networks', NetworkListCreateView.as_view(), name='network-list'),
    path('networks/<int:pk>', NetworkDetailView.as_view(), name='network-detail'),
]
