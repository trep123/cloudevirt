"""任务 API：列表、详情、取消、重试。"""

from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.instances.actions import release_cancelled_task
from apps.tasks.models import Task, TaskStatus
from apps.tasks.serializers import TaskDetailSerializer, TaskSerializer
from apps.tasks.services import record_event
from common.errors import AppError, ErrorCode
from common.permissions import CanCancelTask, CanRetryTask, CanViewTask, RequiresPasswordChange
from common.scope import TaskScopeMixin, tasks_for


class TaskListView(TaskScopeMixin, generics.ListAPIView):
    """任务列表。"""

    permission_classes = [CanViewTask, RequiresPasswordChange]
    queryset = Task.objects.all()
    serializer_class = TaskSerializer


class TaskDetailView(TaskScopeMixin, generics.RetrieveAPIView):
    """任务详情（含事件流水）。"""

    permission_classes = [CanViewTask, RequiresPasswordChange]
    queryset = Task.objects.all()
    serializer_class = TaskDetailSerializer


class TaskCancelView(APIView):
    """取消尚未开始的任务。"""

    permission_classes = [CanCancelTask, RequiresPasswordChange]

    def post(self, request, pk) -> Response:
        """把等待中的任务置为已取消。"""
        task = tasks_for(request.user).filter(pk=pk).first()
        if task is None:
            raise AppError(ErrorCode.NOT_FOUND)
        if task.status != TaskStatus.PENDING:
            raise AppError(
                ErrorCode.CONFLICT,
                '只有等待中的任务可以取消',
                details={'status': task.status},
            )
        task.status = TaskStatus.CANCELLED
        task.finished_at = None
        task.locked_at = None
        task.locked_by = ''
        task.save(update_fields=['status', 'locked_at', 'locked_by', 'updated_at'])
        record_event(task, to_status=TaskStatus.CANCELLED, message='任务被用户取消')
        release_cancelled_task(task)
        if task.type == 'IMAGE_IMPORT' and task.resource_type == 'image':
            from apps.images.models import Image

            Image.objects.filter(pk=task.resource_id, is_deleted=False).update(
                status='FAILED',
                error_code='CONFLICT',
                error_message='镜像校验任务已取消，可以重新校验',
            )
        return Response(TaskDetailSerializer(task).data)


class TaskRetryView(APIView):
    """重试失败的任务。"""

    permission_classes = [CanRetryTask, RequiresPasswordChange]

    def post(self, request, pk) -> Response:
        """把失败任务重新排队。"""
        task = tasks_for(request.user).filter(pk=pk).first()
        if task is None:
            raise AppError(ErrorCode.NOT_FOUND)
        if task.status != TaskStatus.FAILED:
            raise AppError(
                ErrorCode.CONFLICT,
                '只有失败的任务可以重试',
                details={'status': task.status},
            )
        if task.type == 'INSTANCE_SNAPSHOT':
            raise AppError(
                ErrorCode.CONFLICT,
                '请先查询实际快照状态，再在快照页面确认新的操作；不允许直接重放快照任务',
            )
        if task.type == 'ACCOUNT_BATCH':
            raise AppError(
                ErrorCode.CONFLICT,
                '请下载批次结果，修正失败记录后重新预校验；不允许直接重放账号批次',
            )
        task.status = TaskStatus.PENDING
        task.attempt_count = 0
        task.next_retry_at = None
        task.finished_at = None
        task.last_error_code = ''
        task.last_error_message = ''
        task.save(
            update_fields=[
                'status',
                'attempt_count',
                'next_retry_at',
                'finished_at',
                'last_error_code',
                'last_error_message',
                'updated_at',
            ]
        )
        record_event(task, to_status=TaskStatus.PENDING, message='任务被用户重试')
        return Response(TaskDetailSerializer(task).data)
