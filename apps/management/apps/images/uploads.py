"""Bounded browser uploads, node provenance and asynchronous verification."""

from pathlib import PurePath

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.parsers import BaseParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import is_admin
from apps.audit.services import record_audit
from apps.images.models import Image, ImageStatus, ImageUpload
from apps.images.services import allowed_formats, validate_relative_path
from apps.nodes.access import user_can_access
from apps.nodes.client import AgentClient
from apps.nodes.models import Node, NodePermission
from apps.tasks.models import ACTIVE_STATUSES, Task, TaskType
from apps.tasks.services import enqueue
from common.errors import AppError, ErrorCode
from common.permissions import CanImportImage, RequiresPasswordChange

CHUNK_BYTES = 8 * 1024 * 1024


def pool_query(image, prefix='&'):
    from urllib.parse import quote

    query = (
        prefix + 'storage_pool=' + quote(image.storage_pool.name, safe='')
        if image.storage_pool_id
        else ''
    )
    directory = str(PurePath(image.relative_path).parent)
    if directory.startswith('images/user-'):
        query += ('&' if query else prefix) + 'directory=' + quote(directory, safe='')
    return query


def pool_kwargs(image):
    return {'storage_pool': image.storage_pool.name} if image.storage_pool_id else {}


def check_node(user, node, permission='images.add_image'):
    from apps.accounts.administration import limit_nodes

    if not node or not node.is_schedulable:
        raise AppError(ErrorCode.NODE_OFFLINE, '节点不可用，请选择在线节点')
    if not user_can_access(user, node, NodePermission.OPERATE):
        raise AppError(ErrorCode.PERMISSION_DENIED, '没有此节点的操作权限')
    if node.pk not in limit_nodes(user, {node.pk}, permission):
        raise AppError(ErrorCode.PERMISSION_DENIED, '此操作超出角色或用户的节点授权范围')


def image_task(image, user):
    task = enqueue(
        task_type=TaskType.IMAGE_IMPORT,
        resource_type='image',
        resource_id=str(image.pk),
        requested_by=user,
        max_attempts=1,
    )
    image.status, image.error_code, image.error_message = ImageStatus.VERIFYING, '', ''
    image.save(update_fields=['status', 'error_code', 'error_message', 'updated_at'])
    record_audit(
        action='IMAGE_VERIFY_SUBMITTED',
        actor=user,
        target_type='image',
        target_id=str(image.pk),
        task_id=str(task.pk),
        details={'node_id': image.node_id},
    )
    return task


def accepted(image, task):
    from apps.images.serializers import ImageSerializer

    return Response(
        {'image': ImageSerializer(image).data, 'task_id': str(task.pk), 'status': task.status},
        status=202,
    )


@transaction.atomic
def register_image(data, user):
    node = data['node']
    check_node(user, node)
    path = validate_relative_path(data['relative_path'])
    from apps.infrastructure.placement import select_storage_pool

    pool = select_storage_pool(user, node, data.get('storage_pool', ''))
    from apps.instances.models import Disk

    if (
        Disk.objects.filter(instance__node=node, instance__storage_pool=pool, relative_path=path)
        .exclude(status='DELETED')
        .exists()
    ):
        raise AppError(ErrorCode.CONFLICT, '文件已登记为虚拟机磁盘，不能重复登记为镜像')
    try:
        with transaction.atomic():
            image = Image.objects.create(
                name=data['name'],
                node=node,
                relative_path=path,
                storage_pool=pool,
                format='QCOW2',
                created_by=user,
                os_family=data.get('os_family', ''),
                os_version=data.get('os_version', ''),
            )
    except IntegrityError as exc:
        raise AppError(ErrorCode.CONFLICT, '镜像名称或路径已登记，请使用原记录重新校验') from exc
    return image, image_task(image, user)


class UploadInput(serializers.Serializer):
    storage_pool = serializers.CharField(
        max_length=64, required=False, default='', allow_blank=True
    )
    id = serializers.UUIDField()
    name = serializers.CharField(min_length=2, max_length=128)
    node = serializers.PrimaryKeyRelatedField(queryset=Node.objects.filter(is_deleted=False))
    original_name = serializers.CharField(max_length=255)
    size_bytes = serializers.IntegerField(min_value=1)
    os_family = serializers.CharField(max_length=32, allow_blank=True, default='')
    os_version = serializers.CharField(max_length=32, allow_blank=True, default='')

    def validate(self, attrs):
        maximum = min(settings.IMAGE_UPLOAD_MAX_BYTES, 64 * 1024**3)
        if attrs['size_bytes'] > maximum:
            raise serializers.ValidationError(f'镜像超过上传上限 {maximum // 1024**3} GiB')
        extension = PurePath(attrs['original_name']).suffix.lower()
        if extension not in {'.qcow2', '.raw', '.img', '.iso'}:
            raise serializers.ValidationError(
                '仅支持 qcow2、raw、img 或 iso 文件；格式仍由节点实际检测'
            )
        attrs['extension'] = extension
        return attrs


def upload_data(upload, progress=None):
    return {
        'id': str(upload.pk),
        'image_id': upload.image_id,
        'chunk_bytes': CHUNK_BYTES,
        'size_bytes': upload.size_bytes,
        'status': upload.image.status,
        'task_id': str(upload.task_id) if upload.task_id else None,
        **(progress or {}),
    }


def owned_upload(request, pk, *, lock=False):
    queryset = ImageUpload.objects.select_related('image__node').filter(image__is_deleted=False)
    if lock:
        # Do not lock the nullable node side of the JOIN on PostgreSQL.
        queryset = queryset.select_for_update(of=('self',))
    if not is_admin(request.user):
        queryset = queryset.filter(image__created_by=request.user)
    upload = get_object_or_404(queryset, pk=pk)
    check_node(request.user, upload.image.node)
    return upload


def progress_from_agent(upload):
    return AgentClient(upload.image.node.endpoint).get_json(
        f'/api/v1/images/uploads/{upload.pk.hex}?extension={upload.extension}'
        + pool_query(upload.image)
    )


class UploadCreateView(APIView):
    permission_classes = [CanImportImage, RequiresPasswordChange]

    def get(self, request):
        return Response(
            {
                'max_bytes': min(settings.IMAGE_UPLOAD_MAX_BYTES, 64 * 1024**3),
                'chunk_bytes': CHUNK_BYTES,
            }
        )

    @transaction.atomic
    def post(self, request):
        serializer = UploadInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        check_node(request.user, data['node'])
        from apps.infrastructure.placement import select_storage_pool

        selected_pool = select_storage_pool(
            request.user, data['node'], data.get('storage_pool', '')
        )
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        existing = ImageUpload.objects.filter(pk=data['id']).select_related('image').first()
        if existing:
            image = existing.image
            if image.storage_pool_id != (selected_pool.pk if selected_pool else None):
                raise AppError(ErrorCode.CONFLICT, '上传 ID 已绑定其他存储池')
            if image.created_by_id != request.user.pk:
                raise AppError(ErrorCode.NOT_FOUND)
            if image.is_deleted or (
                image.name,
                image.node_id,
                existing.original_name,
                existing.size_bytes,
                image.os_family,
                image.os_version,
            ) != (
                data['name'],
                data['node'].pk,
                data['original_name'],
                data['size_bytes'],
                data['os_family'],
                data['os_version'],
            ):
                raise AppError(ErrorCode.CONFLICT, '上传 ID 已用于不同文件或配置')
            return Response(upload_data(existing))
        if (
            ImageUpload.objects.filter(
                image__created_by=request.user,
                image__is_deleted=False,
                image__status=ImageStatus.UPLOADING,
            ).count()
            >= 3
        ):
            raise AppError(ErrorCode.CONFLICT, '最多同时保留 3 个未完成上传，请先取消旧上传')
        try:
            with transaction.atomic():
                image = Image.objects.create(
                    name=data['name'],
                    node=data['node'],
                    storage_pool=selected_pool,
                    created_by=request.user,
                    relative_path=f'images/user-{request.user.pk}/{data["id"].hex}/upload-{data["id"].hex}{data["extension"]}',
                    format='QCOW2',
                    status=ImageStatus.UPLOADING,
                    os_family=data['os_family'],
                    os_version=data['os_version'],
                )
                upload = ImageUpload.objects.create(
                    id=data['id'],
                    image=image,
                    original_name=data['original_name'],
                    size_bytes=data['size_bytes'],
                    extension=data['extension'],
                )
        except IntegrityError as exc:
            raise AppError(ErrorCode.CONFLICT, '镜像名称或上传 ID 已存在') from exc
        record_audit(
            action='IMAGE_UPLOAD_CREATED',
            actor=request.user,
            target_type='image',
            target_id=str(image.pk),
            details={'size_bytes': upload.size_bytes, 'node_id': image.node_id},
        )
        return Response(upload_data(upload), status=201)


class UploadDetailView(APIView):
    permission_classes = [CanImportImage, RequiresPasswordChange]

    def get(self, request, pk):
        upload = owned_upload(request, pk)
        return Response(upload_data(upload, progress_from_agent(upload)))

    @transaction.atomic
    def delete(self, request, pk):
        upload = owned_upload(request, pk, lock=True)
        if upload.image.status not in {ImageStatus.UPLOADING, ImageStatus.FAILED}:
            raise AppError(ErrorCode.CONFLICT, '上传已进入校验或已完成，请使用镜像删除流程')
        if Task.objects.filter(
            resource_type='image', resource_id=str(upload.image_id), status__in=ACTIVE_STATUSES
        ).exists():
            raise AppError(ErrorCode.OPERATION_IN_PROGRESS, '镜像任务仍在执行')
        AgentClient(upload.image.node.endpoint).request_json(
            f'/api/v1/images/uploads/{upload.pk.hex}?extension={upload.extension}'
            + pool_query(upload.image),
            'DELETE',
        )
        upload.image.is_deleted = True
        upload.image.status = ImageStatus.FAILED
        upload.image.save(update_fields=['is_deleted', 'status', 'updated_at'])
        record_audit(
            action='IMAGE_UPLOAD_CANCELLED',
            actor=request.user,
            target_type='image',
            target_id=str(upload.image_id),
        )
        return Response(status=204)


class ChunkParser(BaseParser):
    media_type = 'application/octet-stream'

    def parse(self, stream, media_type=None, parser_context=None):
        data = stream.read(CHUNK_BYTES + 1)
        if not data or len(data) > CHUNK_BYTES:
            raise AppError(ErrorCode.VALIDATION_ERROR, '分片必须为 1 字节至 8 MiB')
        return data


class UploadChunkView(APIView):
    permission_classes = [CanImportImage, RequiresPasswordChange]
    parser_classes = [ChunkParser]

    @transaction.atomic
    def put(self, request, pk):
        upload = owned_upload(request, pk, lock=True)
        if upload.image.status != ImageStatus.UPLOADING:
            raise AppError(ErrorCode.CONFLICT, '此上传已结束，不可继续写入')
        offset = request.query_params.get('offset', '')
        if not offset.isdecimal():
            raise AppError(ErrorCode.INVALID_ARGUMENT, '分片偏移必须是非负整数')
        data = request.data
        if int(offset) + len(data) > upload.size_bytes:
            raise AppError(ErrorCode.INVALID_ARGUMENT, '分片超出文件总大小')
        result = AgentClient(upload.image.node.endpoint, timeout=120).upload_chunk(
            upload.pk.hex,
            int(offset),
            upload.size_bytes,
            upload.extension,
            data,
            directory=str(PurePath(upload.image.relative_path).parent)
            if upload.image.relative_path.startswith('images/user-')
            else '',
            **pool_kwargs(upload.image),
        )
        upload.save(update_fields=['updated_at'])
        return Response(result)


class UploadCompleteView(APIView):
    permission_classes = [CanImportImage, RequiresPasswordChange]

    @transaction.atomic
    def post(self, request, pk):
        upload = owned_upload(request, pk, lock=True)
        image = Image.objects.select_for_update().get(pk=upload.image_id)
        if upload.task_id:
            return accepted(image, upload.task)
        if image.status != ImageStatus.UPLOADING:
            raise AppError(ErrorCode.CONFLICT, '此上传不可提交')
        progress = progress_from_agent(upload)
        if progress.get('offset') != upload.size_bytes or progress.get('published'):
            raise AppError(ErrorCode.CONFLICT, '文件尚未完整接收，不能提交校验')
        task = image_task(image, request.user)
        upload.task = task
        upload.save(update_fields=['task', 'updated_at'])
        return accepted(image, task)


class ImageVerifyView(APIView):
    permission_classes = [CanImportImage, RequiresPasswordChange]

    @transaction.atomic
    def post(self, request, pk):
        image = get_object_or_404(Image.objects.select_for_update(), pk=pk, is_deleted=False)
        if image.status in {ImageStatus.UPLOADING, ImageStatus.DELETING}:
            raise AppError(ErrorCode.CONFLICT, '请先完成或取消上传')
        active = Task.objects.filter(
            resource_type='image', resource_id=str(image.pk), status__in=ACTIVE_STATUSES
        ).first()
        if active:
            return accepted(image, active)
        node_id = request.data.get('node', image.node_id)
        if not isinstance(node_id, int) or isinstance(node_id, bool):
            raise AppError(ErrorCode.INVALID_ARGUMENT, '请选择镜像文件实际所在的节点')
        node = get_object_or_404(Node, pk=node_id, is_deleted=False)
        check_node(request.user, node)
        if image.node_id and image.node_id != node.pk:
            raise AppError(ErrorCode.CONFLICT, '不能将镜像重新绑定到其他节点')
        if image.instances.filter(is_deleted=False).exclude(node=node).exists():
            raise AppError(ErrorCode.CONFLICT, '已有虚拟机引用其他节点上的旧镜像，无法自动绑定')
        image.node = node
        image.save(update_fields=['node', 'updated_at'])
        return accepted(image, image_task(image, request.user))


def execute_image_import(task):
    image = get_object_or_404(
        Image.objects.select_related('node'), pk=task.resource_id, is_deleted=False
    )
    if image.status == ImageStatus.READY:
        return {'image_id': image.pk, 'status': image.status}
    try:
        if not image.node or not image.node.is_schedulable:
            raise AppError(ErrorCode.NODE_OFFLINE, '镜像所属节点不可用')
        client = AgentClient(image.node.endpoint, timeout=settings.IMAGE_INSPECT_TIMEOUT_SECONDS)
        upload = ImageUpload.objects.filter(image=image).first()
        if upload:
            client.request_json(
                f'/api/v1/images/uploads/{upload.pk.hex}/complete' + pool_query(image, '?'),
                'POST',
                {'size_bytes': upload.size_bytes, 'extension': upload.extension},
            )
        info = client.inspect_image(image.relative_path, **pool_kwargs(image))
        detected = str(info.get('format', '')).upper()
        if detected not in allowed_formats() or int(info.get('size_bytes', 0)) <= 0:
            raise AppError(ErrorCode.VALIDATION_ERROR, '镜像格式不受支持或文件为空')
        if upload and int(info['size_bytes']) != upload.size_bytes:
            raise AppError(ErrorCode.CONFLICT, '镜像大小与上传声明不一致')
    except Exception as error:
        exc = (
            error
            if isinstance(error, AppError)
            else AppError(ErrorCode.OPERATION_FAILED, '镜像校验异常，请检查节点日志后重新校验')
        )
        agent_request_id = (
            exc.details.get('agent_request_id', '') if isinstance(exc.details, dict) else ''
        )
        failure_message = exc.message + (
            f'（节点请求编号：{agent_request_id}）' if agent_request_id else ''
        )
        Image.objects.filter(pk=image.pk, is_deleted=False).update(
            status=ImageStatus.FAILED,
            error_code=exc.code,
            error_message=failure_message,
            updated_at=timezone.now(),
        )
        record_audit(
            action='IMAGE_VERIFY_FAILED',
            actor=task.requested_by,
            target_type='image',
            target_id=str(image.pk),
            task_id=str(task.pk),
            result='FAILURE',
            details={'error_code': exc.code, 'agent_request_id': agent_request_id},
        )
        if isinstance(error, AppError):
            raise
        raise exc from error
    Image.objects.filter(pk=image.pk, is_deleted=False).update(
        status=ImageStatus.READY,
        format=detected,
        size_bytes=int(info['size_bytes']),
        virtual_size_bytes=info.get('virtual_size_bytes'),
        checksum_sha256=info.get('checksum_sha256', ''),
        error_code='',
        error_message='',
        updated_at=timezone.now(),
    )
    record_audit(
        action='IMAGE_VERIFY_COMPLETED',
        actor=task.requested_by,
        target_type='image',
        target_id=str(image.pk),
        task_id=str(task.pk),
    )
    return {
        'image_id': image.pk,
        'status': ImageStatus.READY,
        'checksum_sha256': info.get('checksum_sha256', ''),
    }
