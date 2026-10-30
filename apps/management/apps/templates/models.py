"""实例模板（规格预设）模型。

模板用于在创建实例时快速填充 vCPU / 内存 / 系统盘规格，
不存储镜像与节点信息，由创建时按需选择。
"""

from django.conf import settings
from django.db import models


class Template(models.Model):
    """实例规格模板。"""

    name = models.CharField('名称', max_length=64, unique=True)
    description = models.CharField('说明', max_length=200, blank=True, default='')
    vcpu = models.PositiveIntegerField('vCPU')
    memory_mib = models.PositiveIntegerField('内存(MiB)')
    disk_gib = models.PositiveIntegerField('系统盘(GiB)')
    is_public = models.BooleanField('公开可用', default=True)
    assigned_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='assigned_templates'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='templates',
        verbose_name='创建者',
    )
    is_deleted = models.BooleanField('已删除', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '实例模板'
        verbose_name_plural = '实例模板'
        ordering = ['name']
        indexes = [models.Index(fields=['is_deleted', 'is_public'])]

    def __str__(self) -> str:
        """返回可读标识。"""
        return f'{self.name} ({self.vcpu}C{self.memory_mib}M{self.disk_gib}G)'


class TemplateVersion(models.Model):
    template = models.ForeignKey(Template, on_delete=models.PROTECT, related_name='versions')
    version = models.PositiveIntegerField()
    configuration = models.JSONField(default=dict)
    constraints = models.JSONField(default=dict)
    published = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    image_checksum = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['template', 'version'], name='unique_template_version')
        ]

    def __str__(self):
        return f'{self.template_id}@{self.version}'
