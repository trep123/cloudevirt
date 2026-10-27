"""监控路由。"""

from django.urls import path

from apps.monitoring.views import (
    AlertListView,
    OverviewView,
    ReconciliationRunDetailView,
    ReconciliationRunListView,
    ReconciliationTriggerView,
)

urlpatterns = [
    path('monitoring/overview', OverviewView.as_view(), name='monitoring-overview'),
    path('monitoring/alerts', AlertListView.as_view(), name='monitoring-alerts'),
    path(
        'monitoring/reconciliation', ReconciliationRunListView.as_view(), name='reconciliation-list'
    ),
    path(
        'monitoring/reconciliation/<int:pk>',
        ReconciliationRunDetailView.as_view(),
        name='reconciliation-detail',
    ),
    path(
        'monitoring/reconciliation/run',
        ReconciliationTriggerView.as_view(),
        name='reconciliation-run',
    ),
]
