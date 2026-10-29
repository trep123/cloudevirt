"""网络路由。"""

from django.urls import path

from apps.networks.addresses import IPPoolDetailView, IPPoolsView
from apps.networks.bridges import BridgeCreateView, BridgeRetryView, PhysicalInterfacesView
from apps.networks.views import NetworkDetailView, NetworkListCreateView

urlpatterns = [
    path('networks/nodes/<int:node_id>/physical-interfaces', PhysicalInterfacesView.as_view()),
    path('networks/bridges', BridgeCreateView.as_view()),
    path('networks/<int:pk>/provision', BridgeRetryView.as_view()),
    path('networks/ip-pools', IPPoolsView.as_view()),
    path('networks/ip-pools/<int:pk>', IPPoolDetailView.as_view()),
    path('networks', NetworkListCreateView.as_view(), name='network-list'),
    path('networks/<int:pk>', NetworkDetailView.as_view(), name='network-detail'),
]
