"""监控与对账序列化器。"""

from rest_framework import serializers

from apps.monitoring.models import Alert, ReconciliationDiff, ReconciliationRun


class AlertSerializer(serializers.ModelSerializer):
    """告警输出。"""

    class Meta:
        model = Alert
        fields = (
            'id',
            'type',
            'level',
            'status',
            'message',
            'resource_type',
            'resource_id',
            'count',
            'first_seen_at',
            'last_seen_at',
            'resolved_at',
        )


class ReconciliationDiffSerializer(serializers.ModelSerializer):
    """对账差异输出。"""

    class Meta:
        model = ReconciliationDiff
        fields = (
            'id',
            'kind',
            'resource_type',
            'resource_id',
            'detail',
            'resolution',
            'resolved_at',
            'note',
        )


class ReconciliationRunSerializer(serializers.ModelSerializer):
    """对账批次输出，包含差异明细。"""

    diffs = ReconciliationDiffSerializer(many=True, read_only=True)

    class Meta:
        model = ReconciliationRun
        fields = ('id', 'started_at', 'finished_at', 'status', 'scope', 'summary', 'diffs')
