"""镜像模型与状态字典。

镜像文件存放在节点 Agent 的镜像目录中，数据库只保存相对路径与校验信息，
禁止由用户指定绝对路径。
"""

import uuid

from django.conf import settings
from django.db import models


class ImageFormat(models.TextChoices):
    """允许的镜像格式。"""

    ISO = 'ISO', 'ISO'
    QCOW2 = 'QCOW2', 'QCOW2'
    RAW = 'RAW', 'RAW'


class ImageStatus(models.TextChoices):
    """镜像状态。"""

    UPLOADING = 'UPLOADING', '上传中'
    VERIFYING = 'VERIFYING', '校验中'
    READY = 'READY', '可用'
    FAILED = 'FAILED', '失败'
    DELETING = 'DELETING', '删除中'


class Image(models.Model):
    """镜像记录。"""

    name = models.CharField('名称', max_length=128)
    node = models.ForeignKey(
        'nodes.Node',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='images',
        verbose_name='所属节点',
    )
    format = models.CharField('格式', max_length=16, choices=ImageFormat.choices)
    storage_pool = models.ForeignKey(
        'infrastructure.ManagedStoragePool',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='images',
    )
    relative_path = models.CharField('相对路径', max_length=255)
    size_bytes = models.BigIntegerField('文件大小(字节)', default=0)
    virtual_size_bytes = models.BigIntegerField('虚拟容量(字节)', null=True, blank=True)
    checksum_sha256 = models.CharField('SHA-256', max_length=64, blank=True, default='')
    status = models.CharField(
        '状态', max_length=16, choices=ImageStatus.choices, default=ImageStatus.VERIFYING
    )
    os_family = models.CharField('系统系列', max_length=32, blank=True, default='')
    os_version = models.CharField('系统版本', max_length=32, blank=True, default='')
    supports_cloud_init = models.BooleanField(default=False)
    error_code = models.CharField('错误码', max_length=64, blank=True, default='')
    error_message = models.TextField('错误信息', blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='images',
        verbose_name='创建者',
    )
    is_deleted = models.BooleanField('已删除', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '镜像'
        verbose_name_plural = '镜像'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['is_deleted', 'created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['name'],
                condition=models.Q(is_deleted=False),
                name='uniq_image_name_when_active',
            ),
            models.UniqueConstraint(
                fields=['node', 'storage_pool', 'relative_path'],
                condition=models.Q(is_deleted=False, storage_pool__isnull=False),
                name='uniq_image_path_when_active',
            ),
            models.UniqueConstraint(
                fields=['node', 'relative_path'],
                condition=models.Q(is_deleted=False, storage_pool__isnull=True, node__isnull=False),
                name='uniq_legacy_node_image_path',
            ),
            models.UniqueConstraint(
                fields=['relative_path'],
                condition=models.Q(is_deleted=False, storage_pool__isnull=True, node__isnull=True),
                name='uniq_unbound_image_path',
            ),
        ]

    def __str__(self) -> str:
        """返回可读标识。"""
        return f'{self.name} ({self.format})'

    @property
    def is_ready(self) -> bool:
        """是否可用。"""
        return self.status == ImageStatus.READY and not self.is_deleted


class ImageUpload(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image = models.OneToOneField(Image, on_delete=models.PROTECT, related_name='upload')
    original_name = models.CharField(max_length=255)
    size_bytes = models.BigIntegerField()
    extension = models.CharField(max_length=8)
    task = models.ForeignKey('tasks.Task', on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.pk}:{self.original_name}'
