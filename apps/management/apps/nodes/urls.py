"""节点路由。"""

from django.urls import path

from apps.nodes.views import NodeDetailView, NodeListCreateView, NodeRefreshView

urlpatterns = [
    path('nodes', NodeListCreateView.as_view(), name='node-list'),
    path('nodes/<int:pk>', NodeDetailView.as_view(), name='node-detail'),
    path('nodes/<int:pk>/refresh', NodeRefreshView.as_view(), name='node-refresh'),
]
