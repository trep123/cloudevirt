from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.administration import require_admin
from apps.accounts.roles import is_admin
from apps.audit.services import record_audit
from apps.templates.models import Template, TemplateVersion
from common.permissions import CanViewTemplate, RequiresPasswordChange

CONFIG_FIELDS = {
    'node',
    'initialization',
    'data_disks',
    'additional_networks',
    'hardware',
    'image',
    'vcpu',
    'memory_mib',
    'disk_gib',
    'network_name',
    'autostart',
    'start_after_create',
}


def visible_templates(user):
    query = Template.objects.filter(is_deleted=False)
    return (
        query
        if is_admin(user)
        else query.filter(Q(is_public=True) | Q(assigned_users=user)).distinct()
    )


class VersionSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source='template.name', read_only=True)
    description = serializers.CharField(source='template.description', read_only=True)
    is_public = serializers.BooleanField(source='template.is_public', read_only=True)
    assigned_users = serializers.PrimaryKeyRelatedField(
        source='template.assigned_users', many=True, read_only=True
    )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request is None or not is_admin(request.user):
            fields.pop('assigned_users', None)
        return fields

    class Meta:
        model = TemplateVersion
        fields = [
            'id',
            'template',
            'template_name',
            'description',
            'is_public',
            'assigned_users',
            'version',
            'configuration',
            'constraints',
            'published',
            'created_at',
        ]
        read_only_fields = ['id', 'template', 'version', 'published', 'created_at']

    def validate(self, data):
        config = data.get('configuration', {})
        if not isinstance(config, dict):
            raise serializers.ValidationError({'configuration': '必须是配置对象'})
        from apps.instances.hardware import HardwareSerializer, InitializationSerializer

        if 'initialization' in config:
            initialization = InitializationSerializer(data=config['initialization'])
            initialization.is_valid(raise_exception=True)
            config['initialization'] = initialization.validated_data

        if 'hardware' in config:
            hardware = HardwareSerializer(data=config['hardware'])
            hardware.is_valid(raise_exception=True)
            config['hardware'] = hardware.validated_data
        for key, field in [
            (
                'data_disks',
                serializers.ListField(
                    child=serializers.IntegerField(min_value=1, max_value=2048), max_length=8
                ),
            ),
            (
                'additional_networks',
                serializers.ListField(
                    child=serializers.CharField(max_length=64, allow_blank=False), max_length=7
                ),
            ),
        ]:
            if key in config:
                config[key] = field.run_validation(config[key])
        constraints = data.get('constraints', {})
        if not isinstance(config, dict) or set(config) - CONFIG_FIELDS:
            raise serializers.ValidationError({'configuration': '存在不支持的配置字段'})
        if not isinstance(constraints, dict) or set(constraints) - {'locked', 'bounds'}:
            raise serializers.ValidationError({'constraints': '约束仅支持 locked、bounds'})
        locked = constraints.get('locked', [])
        if not isinstance(locked, list) or any(
            not isinstance(key, str) or key not in config for key in locked
        ):
            raise serializers.ValidationError({'constraints': '锁定项必须是已提供默认值的字段'})
        bounds = constraints.get('bounds', {})
        if not isinstance(bounds, dict) or set(bounds) - {'vcpu', 'memory_mib', 'disk_gib'}:
            raise serializers.ValidationError({'constraints': '数值约束字段无效'})
        for key, limits in bounds.items():
            if (
                not isinstance(limits, dict)
                or set(limits) != {'min', 'max'}
                or any(type(limits[v]) is not int for v in ['min', 'max'])
                or not 0 < limits['min'] <= limits['max']
            ):
                raise serializers.ValidationError({'constraints': f'{key} 上下限无效'})
        for key in ['node', 'image', 'vcpu', 'memory_mib', 'disk_gib']:
            if key in config and (type(config[key]) is not int or config[key] <= 0):
                raise serializers.ValidationError({'configuration': f'{key} 必须为正整数'})
        for key in ['autostart', 'start_after_create']:
            if key in config and type(config[key]) is not bool:
                raise serializers.ValidationError({'configuration': f'{key} 必须为布尔值'})
        if 'network_name' in config and (
            not isinstance(config['network_name'], str) or len(config['network_name']) > 64
        ):
            raise serializers.ValidationError({'configuration': 'network_name 无效'})
        return data


class DeploymentVersionListView(APIView):
    permission_classes = [CanViewTemplate, RequiresPasswordChange]

    def get(self, request):
        versions = (
            TemplateVersion.objects.filter(
                template__in=visible_templates(request.user), published=True, is_deleted=False
            )
            .select_related('template')
            .order_by('template__name', '-version')
        )
        if is_admin(request.user):
            versions = versions.prefetch_related('template__assigned_users')
        return Response(
            {'results': VersionSerializer(versions, many=True, context={'request': request}).data}
        )

    @transaction.atomic
    def post(self, request):
        require_admin(request.user, 'templates.add_template')
        if not isinstance(request.data, dict) or set(request.data) - {
            'name',
            'description',
            'is_public',
            'assigned_users',
            'configuration',
            'constraints',
        }:
            raise serializers.ValidationError('存在未知模板字段')
        payload = request.data.copy()
        config = payload.pop('configuration', {})
        constraints = payload.pop('constraints', {})
        from apps.templates.serializers import TemplateSerializer

        serializer = VersionSerializer(data={'configuration': config, 'constraints': constraints})
        serializer.is_valid(raise_exception=True)
        config = serializer.validated_data.get('configuration', {})
        metadata = TemplateSerializer(
            data={
                **payload,
                **{key: config.get(key) for key in ['vcpu', 'memory_mib', 'disk_gib']},
            },
            context={'request': request},
        )
        metadata.is_valid(raise_exception=True)
        parent = metadata.save(created_by=request.user)
        version = serializer.save(template=parent, version=1)
        result = publish_version(version, request.user)
        result.status_code = 201
        return result


class TemplateVersionView(APIView):
    permission_classes = [RequiresPasswordChange]

    @transaction.atomic
    def post(self, request, pk):
        require_admin(request.user, 'templates.add_template')
        parent = get_object_or_404(Template.objects.select_for_update(), pk=pk, is_deleted=False)
        if set(request.data) - {'configuration', 'constraints'}:
            raise serializers.ValidationError('存在未知模板字段')
        serializer = VersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        latest = parent.versions.order_by('-version').first()
        version = serializer.save(
            template=parent,
            version=(latest.version + 1 if latest else 1),
            configuration={
                'vcpu': parent.vcpu,
                'memory_mib': parent.memory_mib,
                'disk_gib': parent.disk_gib,
                **serializer.validated_data.get('configuration', {}),
            },
        )
        record_audit(
            action='TEMPLATE_VERSION_DRAFT',
            actor=request.user,
            target_type='template',
            target_id=str(pk),
            details={'version': version.version},
        )
        return Response(VersionSerializer(version).data, status=201)


class PublishTemplateVersionView(APIView):
    permission_classes = [RequiresPasswordChange]

    @transaction.atomic
    def post(self, request, pk):
        require_admin(request.user, 'templates.add_template')
        version = get_object_or_404(
            TemplateVersion.objects.select_for_update().select_related('template'),
            pk=pk,
            template__is_deleted=False,
            is_deleted=False,
        )
        return publish_version(version, request.user)


def publish_version(version, user):
    config = {
        'vcpu': version.template.vcpu,
        'memory_mib': version.template.memory_mib,
        'disk_gib': version.template.disk_gib,
        **version.configuration,
    }
    from apps.images.models import Image
    from apps.instances.services import validate_spec
    from apps.networks.services import validate_network_for_instance

    validate_spec(
        name='template-validation',
        vcpu=config['vcpu'],
        memory_mib=config['memory_mib'],
        disk_gib=config['disk_gib'],
    )
    image = Image.objects.filter(pk=config.get('image'), is_deleted=False, status='READY').first()
    if image is None:
        raise serializers.ValidationError({'image': '发布前需指定可用镜像'})
    from apps.nodes.models import Node

    node_id = config.get('node') or image.node_id
    node = None
    if node_id:
        node = get_object_or_404(Node, pk=node_id, is_deleted=False)
        if image.node_id and image.node_id != node.pk:
            raise serializers.ValidationError({'node': '目标节点必须持有所选镜像'})
    from apps.instances.hardware import validate_hardware_policy

    validate_hardware_policy({**config, 'image': image}, user)
    if len(image.checksum_sha256) != 64:
        raise serializers.ValidationError({'image': '镜像需重新登记以获取摘要'})
    for field, bounds in version.constraints.get('bounds', {}).items():
        if not bounds['min'] <= config[field] <= bounds['max']:
            raise serializers.ValidationError({field: '默认值超出模板允许范围'})
    if (
        image.format != 'ISO'
        and image.virtual_size_bytes
        and image.virtual_size_bytes > config['disk_gib'] * 1024**3
    ):
        raise serializers.ValidationError({'disk_gib': '小于镜像虚拟容量'})
    validate_network_for_instance(config.get('network_name', ''), node)
    for name in config.get('additional_networks', []):
        validate_network_for_instance(name, node)
    names = [config.get('network_name')] + config.get('additional_networks', [])
    if len([n for n in names if n]) != len({n for n in names if n}):
        raise serializers.ValidationError({'additional_networks': '网卡网络不能重复'})
    if version.published:
        return Response(VersionSerializer(version).data)
    version.image_checksum = image.checksum_sha256
    version.published = True
    version.save(update_fields=['published', 'image_checksum'])
    record_audit(
        action='TEMPLATE_PUBLISH',
        actor=user,
        target_type='template',
        target_id=str(version.template_id),
        details={'version': version.version},
    )
    return Response(VersionSerializer(version).data)


def resolve_version(data, user):
    version_id = data.get('template_version')
    if not version_id:
        return data
    version = get_object_or_404(
        TemplateVersion.objects.select_related('template'),
        pk=version_id,
        published=True,
        is_deleted=False,
        template__in=visible_templates(user),
    )
    from apps.images.models import Image

    image = Image.objects.filter(
        pk=version.configuration.get('image'),
        checksum_sha256=version.image_checksum,
        status='READY',
        is_deleted=False,
    ).first()
    if image is None:
        raise serializers.ValidationError(
            {'template_version': '模板镜像已变更或不可用，请重新发布版本'}
        )
    defaults = {
        'vcpu': version.template.vcpu,
        'memory_mib': version.template.memory_mib,
        'disk_gib': version.template.disk_gib,
        **version.configuration,
    }
    if 'node' not in defaults and (image.node_id or data.get('node')):
        defaults['node'] = image.node_id or data['node']
    if not defaults.get('node'):
        from apps.accounts.administration import limit_nodes
        from apps.nodes.access import user_can_access
        from apps.nodes.models import Node, NodePermission

        nodes = Node.objects.filter(is_deleted=False).order_by('pk')
        allowed = set(
            limit_nodes(user, list(nodes.values_list('pk', flat=True)), 'instances.add_instance')
        )
        defaults['node'] = next(
            (
                n.pk
                for n in nodes
                if n.pk in allowed
                and n.is_schedulable
                and user_can_access(user, n, NodePermission.OPERATE)
            ),
            None,
        )
    defaults.setdefault('hardware', {})
    defaults.setdefault('data_disks', [])
    defaults.setdefault('autostart', False)
    defaults.setdefault('start_after_create', True)
    for field in CONFIG_FIELDS - {'network_name', 'additional_networks'}:
        if field in data and data[field] != defaults.get(field):
            raise serializers.ValidationError({field: '部署模板配置固定，请由管理员发布新版本'})
    attachments = data.get('additional_networks', defaults.get('additional_networks', []))
    if not isinstance(attachments, list) or len(attachments) != len(
        defaults.get('additional_networks', [])
    ):
        raise serializers.ValidationError(
            {'additional_networks': '网卡数量由模板固定，仅可选择接入网络'}
        )
    config = {**defaults, **data}
    for field in version.constraints.get('locked', []):
        if field in {'network_name', 'additional_networks'}:
            continue
        if config.get(field) != version.configuration.get(field):
            raise serializers.ValidationError({field: '此字段已被模板锁定'})
    if not is_admin(user):
        for field in ['hardware', 'data_disks']:
            if config.get(field, {} if field == 'hardware' else []) != version.configuration.get(
                field, {} if field == 'hardware' else []
            ):
                raise serializers.ValidationError(
                    {field: '硬件配置仅管理员可修改，请使用管理员发布的模板配置'}
                )
    for field, bounds in version.constraints.get('bounds', {}).items():
        value = config.get(field)
        if type(value) is not int or not bounds['min'] <= value <= bounds['max']:
            raise serializers.ValidationError({field: '超出模板允许范围'})
    config['template'] = version.template_id
    return config


class DeploymentVersionDetailView(APIView):
    permission_classes = [RequiresPasswordChange]

    def current(self, pk):
        # Always lock parent before revision, consistent with revision creation.
        original = get_object_or_404(TemplateVersion, pk=pk)
        parent = get_object_or_404(
            Template.objects.select_for_update(), pk=original.template_id, is_deleted=False
        )
        version = get_object_or_404(
            TemplateVersion.objects.select_for_update(), pk=pk, published=True, is_deleted=False
        )
        return parent, version

    @transaction.atomic
    def patch(self, request, pk):
        require_admin(request.user, 'templates.add_template')
        parent, old = self.current(pk)
        allowed = {
            'name',
            'description',
            'is_public',
            'assigned_users',
            'configuration',
            'constraints',
        }
        if not isinstance(request.data, dict) or set(request.data) - allowed:
            raise serializers.ValidationError('存在未知模板字段')
        from copy import deepcopy

        from apps.templates.serializers import TemplateSerializer

        metadata = TemplateSerializer(
            parent,
            data={
                k: v
                for k, v in request.data.items()
                if k in allowed - {'configuration', 'constraints'}
            },
            partial=True,
            context={'request': request},
        )
        metadata.is_valid(raise_exception=True)
        metadata.save()
        serializer = VersionSerializer(
            data={
                'configuration': request.data.get('configuration', deepcopy(old.configuration)),
                'constraints': request.data.get('constraints', deepcopy(old.constraints)),
            }
        )
        serializer.is_valid(raise_exception=True)
        latest = parent.versions.order_by('-version').first()
        version = serializer.save(template=parent, version=latest.version + 1)
        result = publish_version(version, request.user)
        old.is_deleted = True
        old.save(update_fields=['is_deleted'])
        record_audit(
            action='TEMPLATE_VERSION_UPDATE',
            actor=request.user,
            target_type='template',
            target_id=str(parent.pk),
            details={'previous_version': old.version, 'version': version.version},
        )
        return result

    @transaction.atomic
    def delete(self, request, pk):
        require_admin(request.user, 'templates.add_template')
        parent, version = self.current(pk)
        version.is_deleted = True
        version.save(update_fields=['is_deleted'])
        record_audit(
            action='TEMPLATE_VERSION_DELETE',
            actor=request.user,
            target_type='template',
            target_id=str(parent.pk),
            details={'version': version.version},
        )
        return Response(status=204)
