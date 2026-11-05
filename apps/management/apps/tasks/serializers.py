"""任务序列化器。"""

from rest_framework import serializers

from apps.tasks.models import Task, TaskEvent

# Worker JSON can contain initialization data, private paths and node credentials.
# Expose only known diagnostic values; new executor fields are private by default.
PUBLIC_TASK_FIELDS = frozenset(
    {
        'action',
        'batch_id',
        'disk_gib',
        'disk_id',
        'instance_id',
        'instance_uuid',
        'memory_mib',
        'state',
        'storage_pool',
        'vcpu',
        'vlan_id',
    }
)


def public_task_data(data):
    if not isinstance(data, dict):
        return {}
    return {
        key: value
        for key, value in data.items()
        if key in PUBLIC_TASK_FIELDS and isinstance(value, (str, int, float, bool, type(None)))
    }


class TaskEventSerializer(serializers.ModelSerializer):
    """任务事件。"""

    class Meta:
        model = TaskEvent
        fields = (
            'id',
            'attempt',
            'from_status',
            'to_status',
            'level',
            'error_code',
            'message',
            'created_at',
        )


class TaskSerializer(serializers.ModelSerializer):
    """任务列表项。"""

    class Meta:
        model = Task
        fields = (
            'id',
            'type',
            'status',
            'resource_type',
            'resource_id',
            'attempt_count',
            'max_attempts',
            'last_error_code',
            'created_at',
            'updated_at',
        )


class TaskDetailSerializer(TaskSerializer):
    """任务详情，含安全诊断摘要与事件流水。"""

    events = TaskEventSerializer(many=True, read_only=True)
    payload = serializers.SerializerMethodField()
    result = serializers.SerializerMethodField()

    def get_payload(self, task):
        return public_task_data(task.payload)

    def get_result(self, task):
        return public_task_data(task.result)

    class Meta(TaskSerializer.Meta):
        fields = TaskSerializer.Meta.fields + (
            'payload',
            'result',
            'next_retry_at',
            'started_at',
            'finished_at',
            'last_error_message',
            'events',
        )
