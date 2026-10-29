"""�첽����ģ����״̬�ֵ䡣

������ API ��ӣ��ɶ��� worker ԭ����ȡ��ִ�У�
ͬһ��Դ��ͬһʱ��ֻ��������һ��δ��̬����
"""

import uuid

from django.conf import settings
from django.db import models


class TaskStatus(models.TextChoices):
    """����״̬��"""

    PENDING = 'PENDING', '�ȴ�ִ��'
    VALIDATING = 'VALIDATING', 'У����'
    PREPARING = 'PREPARING', '׼����'
    CREATING = 'CREATING', '������'
    VERIFYING = 'VERIFYING', 'У������'
    SUCCEEDED = 'SUCCEEDED', '�ɹ�'
    FAILED = 'FAILED', 'ʧ��'
    CANCELLED = 'CANCELLED', '��ȡ��'
    RECONCILING = 'RECONCILING', '������'


class TaskType(models.TextChoices):
    """�������͡�"""

    NODE_REFRESH = 'NODE_REFRESH', 'ˢ�½ڵ���Դ'
    ACCOUNT_BATCH = 'ACCOUNT_BATCH', '�û����뵼��'
    INSTANCE_CREATE = 'INSTANCE_CREATE', '���������'
    INSTANCE_DISPLAY = 'INSTANCE_DISPLAY', '�޸��������ʾ����'
    INSTANCE_START = 'INSTANCE_START', '���������'
    INSTANCE_SHUTDOWN = 'INSTANCE_SHUTDOWN', '�ر������'
    INSTANCE_FORCE_STOP = 'INSTANCE_FORCE_STOP', 'ǿ��ֹͣ�����'
    INSTANCE_REBOOT = 'INSTANCE_REBOOT', '���������'
    INSTANCE_DELETE = 'INSTANCE_DELETE', 'ɾ�������'
    IMAGE_IMPORT = 'IMAGE_IMPORT', '���뾵��'
    IMAGE_DELETE = 'IMAGE_DELETE', 'ɾ������'
    RECONCILE = 'RECONCILE', '״̬����'
    STORAGE_POOL_CREATE = 'STORAGE_POOL_CREATE', '�����洢��'
    INSTANCE_SNAPSHOT = 'INSTANCE_SNAPSHOT', '���������'


# δ��̬���ɱ�ִ�С����뻥���ж����ݵ�ΨһԼ��
ACTIVE_STATUSES = frozenset(
    {
        TaskStatus.PENDING,
        TaskStatus.VALIDATING,
        TaskStatus.PREPARING,
        TaskStatus.CREATING,
        TaskStatus.VERIFYING,
        TaskStatus.RECONCILING,
    }
)

# ��̬�����ٱ��
TERMINAL_STATUSES = frozenset(
    {
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }
)

# �ɻָ������������޴�����
RETRYABLE_ERROR_CODES = frozenset(
    {
        'NODE_OFFLINE',
        'COMMAND_TIMEOUT',
        'LIBVIRT_UNAVAILABLE',
    }
)


class Task(models.Model):
    """�첽����"""

    id = models.UUIDField('���� ID', primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField('����', max_length=32, choices=TaskType.choices)
    status = models.CharField(
        '״̬', max_length=16, choices=TaskStatus.choices, default=TaskStatus.PENDING
    )
    resource_type = models.CharField('��Դ����', max_length=32)
    resource_id = models.CharField('��Դ��ʶ', max_length=64)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks',
        verbose_name='������',
    )
    idempotency_key = models.CharField('�ݵȼ�', max_length=64, blank=True, default='')
    payload = models.JSONField('�������', default=dict, blank=True)
    result = models.JSONField('ִ�н��', null=True, blank=True)

    attempt_count = models.PositiveIntegerField('�ѳ��Դ���', default=0)
    max_attempts = models.PositiveIntegerField('����Դ���', default=3)
    next_retry_at = models.DateTimeField('�´�����ʱ��', null=True, blank=True)
    locked_at = models.DateTimeField('��ȡʱ��', null=True, blank=True)
    locked_by = models.CharField('��ȡ��', max_length=64, blank=True, default='')

    started_at = models.DateTimeField('��ʼʱ��', null=True, blank=True)
    finished_at = models.DateTimeField('����ʱ��', null=True, blank=True)
    last_error_code = models.CharField('���������', max_length=64, blank=True, default='')
    last_error_message = models.TextField('���������Ϣ', blank=True, default='')
    parent_task = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='������'
    )
    created_at = models.DateTimeField('����ʱ��', auto_now_add=True)
    updated_at = models.DateTimeField('����ʱ��', auto_now=True)

    class Meta:
        verbose_name = '����'
        verbose_name_plural = '����'
        ordering = ['-created_at']
        permissions = [
            ('cancel_task', '����ȡ��δ��ʼ������'),
            ('retry_task', '��������ʧ�ܵ�����'),
        ]
        indexes = [
            models.Index(fields=['status', 'next_retry_at']),
            models.Index(fields=['resource_type', 'resource_id', 'status']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['resource_type', 'resource_id'],
                condition=models.Q(status__in=sorted(ACTIVE_STATUSES)),
                name='uniq_active_task_per_resource',
            ),
            models.UniqueConstraint(
                fields=['idempotency_key'],
                condition=models.Q(status__in=sorted(ACTIVE_STATUSES))
                & ~models.Q(idempotency_key=''),
                name='uniq_active_idempotency_key',
            ),
        ]

    def __str__(self) -> str:
        """���ؿɶ���ʶ��"""
        return f'{self.type}:{self.resource_id} {self.status}'

    @property
    def is_active(self) -> bool:
        """�Ƿ���δ��̬��"""
        return self.status in ACTIVE_STATUSES


class TaskEvent(models.Model):
    """�����¼���ˮ������׷�ٳ�����״̬Ǩ�ơ�"""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='events')
    attempt = models.PositiveIntegerField('�������', default=0)
    from_status = models.CharField('ԭ״̬', max_length=16, blank=True, default='')
    to_status = models.CharField('��״̬', max_length=16, blank=True, default='')
    level = models.CharField('����', max_length=16, default='INFO')
    error_code = models.CharField('������', max_length=64, blank=True, default='')
    message = models.TextField('˵��', blank=True, default='')
    created_at = models.DateTimeField('����ʱ��', auto_now_add=True)

    class Meta:
        verbose_name = '�����¼�'
        verbose_name_plural = '�����¼�'
        ordering = ['created_at']
        indexes = [models.Index(fields=['task', 'created_at'])]

    def __str__(self) -> str:
        """���ؿɶ���ʶ��"""
        return f'{self.task_id} {self.from_status}->{self.to_status} {self.level}'
