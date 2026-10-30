"""Resource organization, live settings and task-backed libvirt operations."""

import hashlib
import uuid
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import is_admin
from apps.audit.services import record_audit
from apps.instances.models import Instance
from apps.nodes.client import AgentClient
from apps.nodes.models import Node
from apps.tasks.models import Task
from apps.tasks.services import enqueue
from common.errors import AppError, ErrorCode
from common.permissions import RequiresPasswordChange, check_permission
from common.scope import instances_for

from .configuration import configuration
from .models import (
    Cluster,
    ClusterNode,
    ConsoleConfiguration,
    ManagedStoragePool,
    PoolInstance,
    ResourcePool,
)


class Administrator(BasePermission):
    def has_permission(self, request, view):
        if not is_admin(request.user):
            raise AppError(ErrorCode.PERMISSION_DENIED, '该功能仅限平台管理员')
        return True


ADMIN_PERMISSIONS = [IsAuthenticated, RequiresPasswordChange, Administrator]


def audit(request, action, target, pk, details=None):
    record_audit(
        action=action,
        actor=request.user,
        target_type=target,
        target_id=str(pk),
        details=details or {},
    )


class ClusterInput(serializers.Serializer):
    name = serializers.RegexField(r'^[\w\- .]{1,64}$')
    description = serializers.CharField(allow_blank=True, max_length=2000, default='')
    node_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), default=list)


class PoolInput(serializers.Serializer):
    name = serializers.RegexField(r'^[\w\- .]{1,64}$')
    description = serializers.CharField(allow_blank=True, max_length=2000, default='')
    cluster_id = serializers.IntegerField(min_value=1)
    vcpu_limit = serializers.IntegerField(min_value=1, max_value=1000000)
    memory_mib_limit = serializers.IntegerField(min_value=1, max_value=2147483647)
    disk_gib_limit = serializers.IntegerField(min_value=1, max_value=2147483647)
    instance_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), default=list)


def usage(instances):
    return {
        key: value or 0
        for key, value in instances.aggregate(
            vcpu=Sum('vcpu'), memory_mib=Sum('memory_mib'), disk_gib=Sum('disk_gib')
        ).items()
    }


def organization_data(kind):
    if kind == 'clusters':
        result = []
        for cluster in Cluster.objects.order_by('name'):
            nodes = Node.objects.filter(clusternode__cluster=cluster, is_deleted=False)
            vms = Instance.objects.filter(node__in=nodes, is_deleted=False)
            result.append(
                {
                    'id': cluster.pk,
                    'name': cluster.name,
                    'description': cluster.description,
                    'node_ids': list(nodes.values_list('id', flat=True)),
                    'nodes': list(
                        nodes.values('id', 'name', 'status', 'resource_is_stale', 'last_seen_at')
                    ),
                    'instances': vms.count(),
                    'usage': usage(vms),
                }
            )
        return result
    return [
        {
            'id': pool.pk,
            'name': pool.name,
            'description': pool.description,
            'cluster_id': pool.cluster_id,
            'cluster_name': pool.cluster.name,
            'vcpu_limit': pool.vcpu_limit,
            'memory_mib_limit': pool.memory_mib_limit,
            'disk_gib_limit': pool.disk_gib_limit,
            'instance_ids': list(
                pool.members.filter(instance__is_deleted=False).values_list(
                    'instance_id', flat=True
                )
            ),
            'usage': usage(Instance.objects.filter(poolinstance__pool=pool, is_deleted=False)),
        }
        for pool in ResourcePool.objects.select_related('cluster').order_by('name')
    ]


class OrganizationView(APIView):
    permission_classes = ADMIN_PERMISSIONS

    def get(self, request, kind, pk=None):
        return Response({'results': organization_data(kind)})

    @transaction.atomic
    def post(self, request, kind, pk=None):
        serializer = (ClusterInput if kind == 'clusters' else PoolInput)(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        model = Cluster if kind == 'clusters' else ResourcePool
        if model.objects.filter(name=data['name']).exclude(pk=pk).exists():
            raise AppError(ErrorCode.CONFLICT, '名称已存在')
        # All membership edits take the same existing cluster locks before node/VM locks.
        list(Cluster.objects.select_for_update().order_by('pk'))
        row = get_object_or_404(model, pk=pk) if pk else model()
        if kind == 'clusters':
            ids = set(data.pop('node_ids'))
            nodes = list(
                Node.objects.select_for_update().filter(pk__in=ids, is_deleted=False).order_by('pk')
            )
            if len(nodes) != len(ids):
                raise AppError(ErrorCode.INVALID_ARGUMENT, '包含不存在的节点')
            if ClusterNode.objects.filter(node_id__in=ids).exclude(cluster_id=row.pk).exists():
                raise AppError(ErrorCode.CONFLICT, '节点已属于其他集群，请先移出')
            if (
                row.pk
                and PoolInstance.objects.filter(pool__cluster=row, instance__is_deleted=False)
                .exclude(instance__node_id__in=ids)
                .exists()
            ):
                raise AppError(ErrorCode.CONFLICT, '移除节点前必须先移出其资源池虚拟机')
            row.name, row.description = data['name'], data['description']
            row.save()
            row.members.exclude(node_id__in=ids).delete()
            for node in nodes:
                ClusterNode.objects.get_or_create(cluster=row, node=node)
        else:
            cluster = get_object_or_404(Cluster, pk=data['cluster_id'])
            ids = set(data.pop('instance_ids'))
            # Membership checks add nullable joins; PostgreSQL may lock only instance rows.
            instances = Instance.objects.select_for_update(of=('self',)).filter(
                pk__in=ids, is_deleted=False
            )
            list(instances.order_by('pk'))
            # Locks acquired above remain until commit; derived EXISTS joins need no new lock.
            instances = Instance.objects.filter(pk__in=ids, is_deleted=False)
            if instances.count() != len(ids):
                raise AppError(ErrorCode.INVALID_ARGUMENT, '包含不存在的虚拟机')
            if instances.exclude(node__clusternode__cluster=cluster).exists():
                raise AppError(ErrorCode.CONFLICT, '虚拟机节点必须属于所选集群')
            if PoolInstance.objects.filter(instance_id__in=ids).exclude(pool_id=row.pk).exists():
                raise AppError(ErrorCode.CONFLICT, '虚拟机已属于其他资源池，请先移出')
            totals = usage(instances)
            if any(totals[key] > data[key + '_limit'] for key in totals):
                raise AppError(ErrorCode.INSUFFICIENT_RESOURCE, '已分配虚拟机资源超出资源池上限')
            for key, value in data.items():
                setattr(row, key, value)
            row.save()
            row.members.exclude(instance_id__in=ids).delete()
            for instance in instances:
                PoolInstance.objects.get_or_create(pool=row, instance=instance)
        audit(request, 'ORGANIZATION_SAVE', kind, row.pk, data)
        return Response({'id': row.pk}, status=200 if pk else 201)

    @transaction.atomic
    def delete(self, request, kind, pk):
        list(Cluster.objects.select_for_update().order_by('pk'))
        model = Cluster if kind == 'clusters' else ResourcePool
        row = get_object_or_404(model, pk=pk)
        if row.members.exists() or (kind == 'clusters' and row.pools.exists()):
            raise AppError(ErrorCode.CONFLICT, '请先移出所有成员及关联资源池')
        row.delete()
        audit(request, 'ORGANIZATION_DELETE', kind, pk)
        return Response(status=204)


class QuotaInput(serializers.Serializer):
    instances = serializers.IntegerField(min_value=1, max_value=1000000)
    vcpu = serializers.IntegerField(min_value=1, max_value=1000000)
    memory_mib = serializers.IntegerField(min_value=1, max_value=2147483647)
    disk_gib = serializers.IntegerField(min_value=1, max_value=2147483647)


class ConfigurationInput(serializers.Serializer):
    revision = serializers.IntegerField(min_value=0)
    quota = QuotaInput()
    storage_warning_percent = serializers.IntegerField(min_value=1, max_value=99)
    storage_critical_percent = serializers.IntegerField(min_value=2, max_value=100)

    def validate(self, attrs):
        if attrs['storage_warning_percent'] >= attrs['storage_critical_percent']:
            raise serializers.ValidationError('警告阈值必须小于高风险阈值')
        return attrs


class SettingsView(APIView):
    permission_classes = ADMIN_PERMISSIONS

    def get(self, request):
        return Response(configuration())

    @transaction.atomic
    def put(self, request):
        serializer = ConfigurationInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        revision = values.pop('revision')
        row, _ = ConsoleConfiguration.objects.get_or_create(pk=1, defaults={'revision': 0})
        row = ConsoleConfiguration.objects.select_for_update().get(pk=row.pk)
        if revision != row.revision:
            raise AppError(ErrorCode.CONFLICT, '配置已被其他管理员修改，请刷新后重新提交')
        row.values, row.revision = values, revision + 1
        row.save()
        audit(request, 'SETTINGS_UPDATE', 'settings', 1, values)
        return Response(configuration())


class PoolCreateInput(serializers.Serializer):
    name = serializers.RegexField(r'^cv-[A-Za-z0-9][A-Za-z0-9_-]{0,55}$')
    path = serializers.CharField(max_length=4096, required=False, allow_blank=True)
    assigned_user_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), max_length=500, required=False, default=list
    )
    default_user_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), max_length=500, required=False, default=list
    )
    is_default = serializers.BooleanField(default=False)

    def validate_path(self, value):
        import posixpath

        if value and (
            not value.startswith('/')
            or '\\' in value
            or '\x00' in value
            or '..' in value.split('/')
        ):
            raise serializers.ValidationError('请输入不含路径穿越的 Linux 绝对目录')
        return posixpath.normpath(value) if value else ''

    def validate_assigned_user_ids(self, value):
        if len(set(value)) != len(value) or get_user_model().objects.filter(
            pk__in=value, is_active=True
        ).count() != len(value):
            raise serializers.ValidationError('用户 ID 重复、不存在或已禁用')
        return value

    def validate_default_user_ids(self, value):
        return self.validate_assigned_user_ids(value)

    def validate(self, data):
        if set(data['default_user_ids']) - set(data['assigned_user_ids']):
            raise serializers.ValidationError(
                {'default_user_ids': '默认用户必须先获得此池的使用授权'}
            )
        return data


def node_for(pk):
    node = get_object_or_404(Node, pk=pk, is_deleted=False)
    if not node.is_schedulable:
        raise AppError(ErrorCode.NODE_OFFLINE)
    return node


def task_response(request, *, task_type, resource_type, resource_id, payload):
    key = request.headers.get('Idempotency-Key', '')
    if not key or len(key) > 128:
        raise AppError(ErrorCode.INVALID_ARGUMENT, '必须提供不超过 128 字符的 Idempotency-Key')
    digest = hashlib.sha256(f'{request.user.pk}:{key}'.encode()).hexdigest()
    previous = Task.objects.filter(idempotency_key=digest).first()
    if previous:
        if (
            previous.type != task_type
            or previous.resource_id != str(resource_id)
            or previous.payload != payload
        ):
            raise AppError(ErrorCode.CONFLICT, '幂等键已用于不同请求')
        task = previous
    else:
        if task_type == 'INSTANCE_SNAPSHOT':
            from apps.instances.actions import ensure_no_active_task

            ensure_no_active_task(Instance.objects.get(pk=resource_id))
        task = enqueue(
            task_type=task_type,
            resource_type=resource_type,
            resource_id=str(resource_id),
            requested_by=request.user,
            payload=payload,
            idempotency_key=digest,
            max_attempts=1,
        )
        audit(request, task_type, resource_type, resource_id, {'task_id': str(task.pk), **payload})
    return Response({'task_id': str(task.pk), 'status': task.status}, status=202)


class StoragePoolsView(APIView):
    permission_classes = ADMIN_PERMISSIONS

    def get(self, request, node_id):
        node = node_for(node_id)
        data = AgentClient(node.endpoint).get_json('/api/v1/storage-pools')
        managed = {
            pool.name: pool
            for pool in ManagedStoragePool.objects.filter(node=node).prefetch_related(
                'allowed_users', 'default_users'
            )
        }
        for row in data.get('results', []):
            pool = managed.get(row.get('name'))
            row['managed'] = pool is not None
            row['assigned_user_ids'] = (
                list(pool.allowed_users.values_list('id', flat=True)) if pool else []
            )
            row['default_user_ids'] = (
                list(pool.default_users.values_list('id', flat=True)) if pool else []
            )
            row['is_default'] = pool.is_default if pool else False
            row['revision'] = pool.revision if pool else None
        return Response(data)

    @transaction.atomic
    def post(self, request, node_id):
        node = get_object_or_404(Node.objects.select_for_update(), pk=node_id, is_deleted=False)
        node_for(node.pk)
        serializer = PoolCreateInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return task_response(
            request,
            task_type='STORAGE_POOL_CREATE',
            resource_type='node',
            resource_id=node.pk,
            payload=dict(serializer.validated_data),
        )


class StoragePoolAccessView(APIView):
    permission_classes = ADMIN_PERMISSIONS

    @transaction.atomic
    def delete(self, request, node_id, name):
        node = get_object_or_404(Node.objects.select_for_update(), pk=node_id, is_deleted=False)
        pool = get_object_or_404(
            ManagedStoragePool.objects.select_for_update(), node=node, name=name
        )
        from apps.instances.models import Disk, ResourceReservation

        if (
            pool.instances.filter(is_deleted=False).exists()
            or pool.images.filter(is_deleted=False).exists()
            or Disk.objects.filter(instance__storage_pool=pool).exclude(status='DELETED').exists()
            or pool.reservations.filter(status='HELD').exists()
        ):
            raise AppError(ErrorCode.CONFLICT, '存储池仍有关联虚拟机、保留磁盘或资源预留，不能删除')
        if not node.is_schedulable:
            raise AppError(ErrorCode.NODE_OFFLINE)
        result = AgentClient(node.endpoint, timeout=180).request_json(
            '/api/v1/storage-pools',
            'POST',
            {'name': pool.name, 'path': pool.path, 'action': 'delete'},
        )
        if result.get('deleted') is not True:
            raise AppError(ErrorCode.CONFLICT, '节点未确认存储池删除')
        pool.instances.update(storage_pool=None)
        pool.images.update(storage_pool=None)
        ResourceReservation.objects.filter(storage_pool=pool).update(storage_pool=None)
        audit(
            request,
            'STORAGE_POOL_DELETE',
            'storage_pool',
            pool.pk,
            {'name': name, 'path': pool.path},
        )
        pool.delete()
        return Response({'deleted': True})

    @transaction.atomic
    def put(self, request, node_id, name):
        node = get_object_or_404(Node.objects.select_for_update(), pk=node_id, is_deleted=False)
        pool = get_object_or_404(
            ManagedStoragePool.objects.select_for_update(), node=node, name=name
        )
        form = PoolCreateInput(
            data={
                'name': pool.name,
                'path': pool.path,
                'assigned_user_ids': request.data.get('assigned_user_ids'),
                'default_user_ids': request.data.get('default_user_ids', []),
                'is_default': request.data.get('is_default'),
            }
        )
        form.is_valid(raise_exception=True)
        revision = request.data.get('revision')
        if type(revision) is not int or revision != pool.revision:
            raise AppError(ErrorCode.CONFLICT, '存储池授权已变化，请刷新后重试')
        if form.validated_data['is_default']:
            ManagedStoragePool.objects.filter(node=node, is_default=True).exclude(
                pk=pool.pk
            ).update(is_default=False)
        pool.is_default = form.validated_data['is_default']
        pool.revision += 1
        pool.save(update_fields=['is_default', 'revision'])
        pool.allowed_users.set(form.validated_data['assigned_user_ids'])
        default_ids = form.validated_data['default_user_ids']
        for other in ManagedStoragePool.objects.filter(node=node).exclude(pk=pool.pk):
            other.default_users.remove(*default_ids)
        pool.default_users.set(default_ids)
        audit(
            request,
            'STORAGE_POOL_ACCESS_UPDATE',
            'storage_pool',
            pool.pk,
            {
                'name': pool.name,
                'users': form.validated_data['assigned_user_ids'],
                'default_users': default_ids,
                'is_default': pool.is_default,
            },
        )
        return Response(
            {
                'name': pool.name,
                'assigned_user_ids': form.validated_data['assigned_user_ids'],
                'default_user_ids': default_ids,
                'is_default': pool.is_default,
                'revision': pool.revision,
            }
        )


class AvailableStoragePoolsView(APIView):
    permission_classes = [IsAuthenticated, RequiresPasswordChange]

    def get(self, request):
        permission = (
            'images.add_image'
            if request.query_params.get('purpose') == 'images'
            else 'instances.add_instance'
        )
        check_permission(request.user, permission)
        node_id = request.query_params.get('node')
        if not node_id or not node_id.isdecimal():
            raise AppError(ErrorCode.INVALID_ARGUMENT, '请指定节点 ID')
        node = get_object_or_404(Node, pk=int(node_id), is_deleted=False)
        from apps.accounts.administration import limit_nodes
        from apps.nodes.access import user_can_access
        from apps.nodes.models import NodePermission

        if node.pk not in limit_nodes(request.user, [node.pk], permission) or not user_can_access(
            request.user, node, NodePermission.OPERATE
        ):
            raise AppError(ErrorCode.PERMISSION_DENIED)
        pools = ManagedStoragePool.objects.filter(node=node)
        if not is_admin(request.user):
            pools = pools.filter(allowed_users=request.user)
            if pools.filter(default_users=request.user).exists():
                pools = pools.filter(default_users=request.user)
        listing = AgentClient(node.endpoint).get_json('/api/v1/storage-pools')
        live = {
            item.get('name')
            for item in listing.get('results', [])
            if item.get('active') and item.get('type') == 'dir'
        }
        rows = list(
            pools.filter(name__in=live).order_by('name').values('name', 'path', 'is_default')
        )
        if not is_admin(request.user):
            personal = set(pools.filter(default_users=request.user).values_list('name', flat=True))
            if personal:
                for row in rows:
                    row['is_default'] = row['name'] in personal
        default = next((row['name'] for row in rows if row['is_default']), '')
        if not default and len(rows) == 1:
            default = rows[0]['name']
        return Response(
            {
                'results': rows,
                'default': default,
                'legacy_available': is_admin(request.user) or not pools.exists(),
            }
        )


class SnapshotInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=['create', 'revert', 'delete'])
    name = serializers.RegexField(r'^cv-[A-Za-z0-9][A-Za-z0-9_-]{0,55}$', required=False)


class SnapshotsView(APIView):
    permission_classes = [IsAuthenticated, RequiresPasswordChange]

    def get(self, request, instance_id):
        check_permission(request.user, 'instances.view_instance')
        instance = get_object_or_404(instances_for(request.user), pk=instance_id)
        return Response(
            AgentClient(instance.node.endpoint).get_json(
                f'/api/v1/domains/{quote(instance.libvirt_domain_name, safe="")}/snapshots'
                + (
                    f'?storage_pool={quote(instance.storage_pool.name, safe="")}'
                    if instance.storage_pool_id
                    else ''
                )
            )
        )

    @transaction.atomic
    def post(self, request, instance_id):
        visible = get_object_or_404(instances_for(request.user), pk=instance_id)
        Node.objects.select_for_update().get(pk=visible.node_id)
        instance = Instance.objects.select_for_update().get(pk=visible.pk, is_deleted=False)
        check_permission(
            request.user,
            'instances.manage_snapshot_instance',
            target_type='instance',
            target_id=str(instance.pk),
        )
        node_for(instance.node_id)
        serializer = SnapshotInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data['action'] != 'create' and 'name' not in data:
            raise AppError(ErrorCode.INVALID_ARGUMENT, '必须指定目标快照')
        # Stable generated names are derived from the request key, so retries reuse the snapshot.
        key = request.headers.get('Idempotency-Key', '')
        name = (
            data.get('name')
            or 'cv-' + uuid.uuid5(uuid.NAMESPACE_URL, f'{instance.pk}:{request.user.pk}:{key}').hex
        )
        if instance.observed_state != 'SHUTOFF' or instance.observed_state_is_stale:
            raise AppError(ErrorCode.CONFLICT, '请先正常关机并等待状态同步后操作快照')
        return task_response(
            request,
            task_type='INSTANCE_SNAPSHOT',
            resource_type='instance',
            resource_id=instance.pk,
            payload={'action': data['action'], 'name': name},
        )
