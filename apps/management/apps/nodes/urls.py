"""节点路由。"""

from django.urls import path

from apps.nodes.views import (
    NodeAccessDetailView,
    NodeAccessListCreateView,
    NodeCapabilitiesView,
    NodeDetailView,
    NodeListCreateView,
    NodeRefreshView,
)

urlpatterns = [
    path('nodes/<int:pk>/capabilities', NodeCapabilitiesView.as_view()),
    path('nodes', NodeListCreateView.as_view(), name='node-list'),
    path('nodes/<int:pk>', NodeDetailView.as_view(), name='node-detail'),
    path('nodes/<int:pk>/refresh', NodeRefreshView.as_view(), name='node-refresh'),
    path('node-access', NodeAccessListCreateView.as_view(), name='node-access-list'),
    path('node-access/<int:pk>', NodeAccessDetailView.as_view(), name='node-access-detail'),
]
