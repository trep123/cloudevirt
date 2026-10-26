"""节点序列化器。"""

from rest_framework import serializers

from apps.nodes.models import Node, NodeStatus


class NodeSerializer(serializers.ModelSerializer):
    """节点输出结构，包含采样时间与过期标记。"""

    is_schedulable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Node
        fields = (
            'id',
            'name',
            'endpoint',
            'status',
            'maintenance_note',
            'agent_version',
            'cpu_total',
            'memory_total_mib',
            'memory_available_mib',
            'storage_total_bytes',
            'storage_free_bytes',
            'resource_sampled_at',
            'resource_is_stale',
            'last_seen_at',
            'consecutive_failures',
            'last_error_code',
            'last_error_message',
            'heartbeat_interval_seconds',
            'offline_after_seconds',
            'is_schedulable',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'status',
            'agent_version',
            'cpu_total',
            'memory_total_mib',
            'memory_available_mib',
            'storage_total_bytes',
            'storage_free_bytes',
            'resource_sampled_at',
            'resource_is_stale',
            'last_seen_at',
            'consecutive_failures',
            'last_error_code',
            'last_error_message',
            'created_at',
            'updated_at',
        )

    def validate_name(self, value: str) -> str:
        """校验节点名字符集与长度。"""
        if len(value) < 2:
            raise serializers.ValidationError('节点名称至少 2 个字符')
        if not value.replace('-', '').replace('_', '').isalnum():
            raise serializers.ValidationError('节点名称只能包含字母、数字、连字符与下划线')
        return value


class NodeCreateSerializer(NodeSerializer):
    """注册节点。"""

    class Meta(NodeSerializer.Meta):
        fields = NodeSerializer.Meta.fields
        read_only_fields = tuple(
            field for field in NodeSerializer.Meta.read_only_fields if field not in {'status'}
        )


class NodeUpdateSerializer(NodeSerializer):
    """更新节点可维护字段（维护态说明与阈值）。"""

    status = serializers.ChoiceField(choices=NodeStatus.choices, required=False)

    class Meta(NodeSerializer.Meta):
        fields = (
            'id',
            'name',
            'endpoint',
            'status',
            'maintenance_note',
            'heartbeat_interval_seconds',
            'offline_after_seconds',
        )
        read_only_fields = ('id',)
