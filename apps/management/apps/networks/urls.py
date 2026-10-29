"""网络路由。"""

from django.urls import path

from apps.networks.addresses import IPPoolDetailView, IPPoolsView
from apps.networks.views import NetworkDetailView, NetworkListCreateView

urlpatterns = [
    path('networks/ip-pools', IPPoolsView.as_view()),
    path('networks/ip-pools/<int:pk>', IPPoolDetailView.as_view()),
    path('networks', NetworkListCreateView.as_view(), name='network-list'),
    path('networks/<int:pk>', NetworkDetailView.as_view(), name='network-detail'),
]
