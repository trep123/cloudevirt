"""任务序列化器。"""

from rest_framework import serializers

from apps.tasks.models import Task, TaskEvent


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
    """任务详情，含参数快照、结果与事件流水。"""

    events = TaskEventSerializer(many=True, read_only=True)

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
