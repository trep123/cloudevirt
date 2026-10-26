"""镜像导入与删除服务。

导入流程（MVP 采用“登记节点已有文件”的方式）：
1) 校验相对路径合法性；
2) 调用节点 Agent 检查文件（路径边界、qemu-img 格式、SHA-256）；
3) 校验格式在允许列表内；
4) 写入数据库（READY）或记录失败原因（FAILED）。
"""

import logging
import re

from django.conf import settings

from apps.images.models import Image, ImageFormat, ImageStatus
from apps.nodes.client import AgentClient
from apps.nodes.models import Node
from common.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

# 相对路径只允许字母数字、点、连字符、下划线与目录分隔符
RELATIVE_PATH_PATTERN = re.compile(r'^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$')


def allowed_formats() -> list[str]:
    """返回允许的镜像格式列表。"""
    configured = getattr(settings, 'IMAGE_ALLOWED_FORMATS', None)
    if configured:
        return list(configured)
    return [ImageFormat.ISO, ImageFormat.QCOW2, ImageFormat.RAW]


def validate_relative_path(relative_path: str) -> str:
    """校验相对路径，拒绝绝对路径与目录穿越。

    Args:
        relative_path: 用户提交的相对路径。

    Returns:
        原样返回的合法路径。

    Raises:
        AppError: 路径非法时抛出 VALIDATION_ERROR。
    """
    candidate = (relative_path or '').strip()
    if not candidate:
        raise AppError(ErrorCode.VALIDATION_ERROR, '镜像路径不能为空')
    if candidate.startswith('/') or '..' in candidate.split('/'):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            '镜像路径必须是相对路径且不包含 ..',
            details={'relative_path': ['仅允许镜像目录内的相对路径']},
        )
    if not RELATIVE_PATH_PATTERN.match(candidate):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            '镜像路径包含非法字符',
            details={'relative_path': ['只允许字母、数字、点、连字符、下划线与 /']},
        )
    return candidate


def import_image(
    *,
    name: str,
    node: Node,
    relative_path: str,
    created_by=None,
    os_family: str = '',
    os_version: str = '',
    client: AgentClient | None = None,
) -> Image:
    """导入（登记）镜像：调用 Agent 检查文件并落库。

    Args:
        name: 镜像名称。
        node: 执行检查的节点。
        relative_path: 镜像目录内的相对路径。
        created_by: 创建者。
        os_family: 系统系列。
        os_version: 系统版本。
        client: Agent 客户端，缺省按节点创建（测试可注入）。

    Returns:
        导入后的镜像对象（READY 或 FAILED）。

    Raises:
        AppError: 参数非法、节点不可用或格式不受支持。
    """
    path = validate_relative_path(relative_path)
    if node.status == 'OFFLINE':
        raise AppError(ErrorCode.NODE_OFFLINE, '节点离线，无法导入镜像')

    image = Image.objects.create(
        name=name,
        format=ImageFormat.QCOW2,
        relative_path=path,
        status=ImageStatus.VERIFYING,
        os_family=os_family,
        os_version=os_version,
        created_by=created_by if created_by and created_by.pk else None,
    )

    agent = client or AgentClient(node.endpoint)
    try:
        info = agent.inspect_image(path)
        detected = str(info.get('format') or '').upper()
        if detected not in allowed_formats():
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                '不支持的镜像格式',
                details={'format': [f'检测到的格式为 {detected or "未知"}']},
            )
    except AppError as exc:
        image.status = ImageStatus.FAILED
        image.error_code = exc.code
        image.error_message = exc.message
        image.save(update_fields=['status', 'error_code', 'error_message', 'updated_at'])
        logger.warning(
            '镜像导入失败',
            extra={'image_id': image.pk, 'error_code': exc.code, 'result': 'failure'},
        )
        raise

    image.format = detected
    image.size_bytes = int(info.get('size_bytes') or 0)
    image.virtual_size_bytes = info.get('virtual_size_bytes')
    image.checksum_sha256 = str(info.get('checksum_sha256') or '')
    image.status = ImageStatus.READY
    image.error_code = ''
    image.error_message = ''
    image.save()
    logger.info('镜像导入成功', extra={'image_id': image.pk, 'result': 'success'})
    return image


def delete_image(
    image: Image,
    *,
    purge_file: bool = True,
    node: Node | None = None,
    client: AgentClient | None = None,
) -> Image:
    """删除镜像记录，并按选择请求 Agent 删除文件。

    Args:
        image: 目标镜像。
        purge_file: 是否同时删除节点上的文件（需 Agent 开启破坏性开关）。
        node: 执行删除的节点，缺省取第一个在线节点。
        client: Agent 客户端，缺省按节点创建。

    Returns:
        更新后的镜像对象。

    Raises:
        AppError: 未指定节点或 Agent 拒绝删除。
    """
    references = image.instances.filter(is_deleted=False).count()
    if references:
        raise AppError(
            ErrorCode.IMAGE_IN_USE,
            '镜像被实例引用，禁止删除',
            details={'instances': references},
        )

    image.status = ImageStatus.DELETING
    image.save(update_fields=['status', 'updated_at'])

    if purge_file:
        target = node or Node.objects.filter(is_deleted=False).exclude(status='OFFLINE').first()
        if target is None:
            image.status = ImageStatus.FAILED
            image.error_code = ErrorCode.NODE_OFFLINE
            image.error_message = '没有可用节点执行删除'
            image.save(update_fields=['status', 'error_code', 'error_message', 'updated_at'])
            raise AppError(ErrorCode.NODE_OFFLINE, '没有可用节点执行删除')
        agent = client or AgentClient(target.endpoint)
        try:
            agent.delete_image(image.relative_path)
        except AppError as exc:
            image.status = ImageStatus.FAILED
            image.error_code = exc.code
            image.error_message = exc.message
            image.save(update_fields=['status', 'error_code', 'error_message', 'updated_at'])
            raise

    image.is_deleted = True
    image.status = ImageStatus.DELETING
    image.save(update_fields=['is_deleted', 'status', 'updated_at'])
    logger.info('镜像已删除', extra={'image_id': image.pk, 'purge_file': purge_file})
    return image
