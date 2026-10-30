"""Console dashboard aggregates only authorized resources and observed metrics."""

from datetime import timedelta

from django.db.models import ExpressionWrapper, F, FloatField, Sum
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import is_admin
from apps.audit.models import AuditEvent
from apps.monitoring.models import Alert
from apps.monitoring.serializers import AlertSerializer
from apps.nodes.access import accessible_node_ids
from apps.nodes.models import Node
from apps.tasks.serializers import TaskSerializer
from common.permissions import RequiresPasswordChange
from common.scope import instances_for, tasks_for


class DashboardView(APIView):
    permission_classes = [IsAuthenticated, RequiresPasswordChange]

    def get(self, request):
        nodes = Node.objects.filter(is_deleted=False, id__in=accessible_node_ids(request.user))
        instances = instances_for(request.user)
        totals = nodes.filter(resource_is_stale=False).aggregate(
            memory=Sum('memory_total_mib'), available=Sum('memory_available_mib')
        )
        memory = totals['memory']
        memory_percent = (
            round(100 * (memory - totals['available']) / memory, 1)
            if memory and totals['available'] is not None
            else None
        )
        admin = is_admin(request.user)
        cpu_nodes = nodes.filter(
            resource_is_stale=False,
            status__in=['ONLINE', 'DEGRADED'],
            cpu_total__gt=0,
            cpu_usage_percent__gte=0,
            cpu_usage_percent__lte=100,
            cpu_sampled_at__gte=timezone.now() - timedelta(seconds=60),
            cpu_sampled_at__lte=timezone.now(),
        )
        cpu = cpu_nodes.aggregate(
            weighted=Sum(
                ExpressionWrapper(
                    F('cpu_usage_percent') * F('cpu_total'), output_field=FloatField()
                )
            ),
            cores=Sum('cpu_total'),
        )
        cpu_percent = round(cpu['weighted'] / cpu['cores'], 1) if cpu['cores'] else None
        return Response(
            {
                'scope': 'admin' if admin else 'user',
                'sampled_at': timezone.now(),
                'nodes': {'total': nodes.count(), 'online': nodes.filter(status='ONLINE').count()},
                'instances': {
                    'total': instances.count(),
                    'running': instances.filter(observed_state='RUNNING').count(),
                },
                'cpu_percent': cpu_percent if admin else None,
                'cpu_sampled_nodes': cpu_nodes.count() if admin else 0,
                'memory_percent': memory_percent if admin else None,
                'trends': [],
                'alerts': AlertSerializer(
                    Alert.objects.filter(status='ACTIVE')[:10], many=True
                ).data
                if admin
                else [],
                'tasks': TaskSerializer(
                    tasks_for(request.user).order_by('-created_at')[:10], many=True
                ).data,
            }
        )


class AuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = (
            'id',
            'actor_username',
            'action',
            'target_type',
            'target_id',
            'result',
            'request_id',
            'task_id',
            'created_at',
        )


class AuditListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, RequiresPasswordChange]
    serializer_class = AuditSerializer

    def get_queryset(self):
        queryset = AuditEvent.objects.all()
        if not is_admin(self.request.user):
            queryset = queryset.filter(actor=self.request.user)
        search = self.request.query_params.get('search', '')
        if search:
            queryset = queryset.filter(action__icontains=search)
        return queryset.order_by('-created_at', '-pk')


class QuotaView(APIView):
    permission_classes = [IsAuthenticated, RequiresPasswordChange]

    def get(self, request):
        from common.quota import quota_for

        return Response(quota_for(request.user))
