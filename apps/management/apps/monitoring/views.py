"""监控 API：概览、告警、对账。"""

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.monitoring.models import Alert, ReconciliationRun
from apps.monitoring.serializers import (
    AlertSerializer,
    ReconciliationRunSerializer,
)
from apps.monitoring.services import overview, run_reconciliation
from common.permissions import CanRunReconciliation, CanViewMonitoring, RequiresPasswordChange


class OverviewView(APIView):
    """监控概览：节点/实例状态分布、活跃告警与最近对账。"""

    permission_classes = [CanViewMonitoring, RequiresPasswordChange]

    def get(self, request) -> Response:
        """返回概览数据。"""
        return Response(overview())


class AlertListView(generics.ListAPIView):
    """告警列表，可按状态与级别过滤。"""

    permission_classes = [CanViewMonitoring, RequiresPasswordChange]
    serializer_class = AlertSerializer

    def get_queryset(self):
        """按查询参数过滤。"""
        queryset = Alert.objects.all()
        alert_status = self.request.query_params.get('status')
        if alert_status:
            queryset = queryset.filter(status=alert_status.upper())
        level = self.request.query_params.get('level')
        if level:
            queryset = queryset.filter(level=level.upper())
        return queryset


class ReconciliationRunListView(generics.ListAPIView):
    """对账批次列表。"""

    permission_classes = [CanViewMonitoring, RequiresPasswordChange]
    queryset = ReconciliationRun.objects.all()
    serializer_class = ReconciliationRunSerializer


class ReconciliationRunDetailView(generics.RetrieveAPIView):
    """对账批次详情（含差异）。"""

    permission_classes = [CanViewMonitoring, RequiresPasswordChange]
    queryset = ReconciliationRun.objects.prefetch_related('diffs')
    serializer_class = ReconciliationRunSerializer


class ReconciliationTriggerView(APIView):
    """手动触发一次对账（管理动作）。"""

    permission_classes = [CanRunReconciliation, RequiresPasswordChange]

    def post(self, request) -> Response:
        """立即对全部节点执行对账并返回结果。"""
        from apps.audit.models import AuditAction
        from apps.audit.services import record_audit

        run = run_reconciliation(requested_by=request.user)
        record_audit(
            action=AuditAction.RECONCILE_RUN,
            actor=request.user,
            target_type='reconciliation',
            target_id=str(run.pk),
            details={'summary': run.summary, 'status': run.status},
        )
        return Response(
            ReconciliationRunSerializer(run).data,
            status=status.HTTP_202_ACCEPTED,
        )
