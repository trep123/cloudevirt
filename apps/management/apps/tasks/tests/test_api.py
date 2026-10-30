"""任务 API 权限与操作测试。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.accounts.roles import sync_role_permissions
from apps.tasks.models import Task, TaskStatus, TaskType
from apps.tasks.services import enqueue


class TaskApiTests(TestCase):
    """任务列表、详情、取消与重试的权限边界。"""

    def setUp(self) -> None:
        """同步角色并创建操作员与只读用户。"""
        sync_role_permissions()
        user_model = get_user_model()
        self.operator = user_model.objects.create_user(
            username='task-operator', password='Str0ngPassw0rd'
        )
        self.operator.groups.add(Group.objects.get(name='Operator'))
        self.viewer = user_model.objects.create_user(
            username='task-viewer', password='Str0ngPassw0rd'
        )
        self.viewer.groups.add(Group.objects.get(name='Viewer'))
        self.task = enqueue(
            task_type=TaskType.NODE_REFRESH,
            resource_type='node',
            resource_id='1',
            requested_by=self.operator,
        )

    def test_unauthenticated_returns_401(self) -> None:
        """未认证应返回 401。"""
        self.assertEqual(self.client.get('/api/v1/tasks').status_code, 401)

    def test_viewer_can_list_tasks(self) -> None:
        """Viewer 可以查看任务列表。"""
        self.client.login(username='task-viewer', password='Str0ngPassw0rd')

        response = self.client.get('/api/v1/tasks')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 0)

    def test_task_detail_includes_events(self) -> None:
        """详情应包含事件流水。"""
        self.client.login(username='task-operator', password='Str0ngPassw0rd')

        response = self.client.get(f'/api/v1/tasks/{self.task.pk}')

        self.assertEqual(response.status_code, 200)
        self.assertIn('events', response.json())

    def test_operator_can_cancel_pending_task(self) -> None:
        """Operator 可以取消等待中的任务。"""
        self.client.login(username='task-operator', password='Str0ngPassw0rd')

        response = self.client.post(f'/api/v1/tasks/{self.task.pk}/cancel')

        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.CANCELLED)

    def test_viewer_cannot_cancel_task(self) -> None:
        """Viewer 无取消权限应返回 403。"""
        self.client.login(username='task-viewer', password='Str0ngPassw0rd')

        response = self.client.post(f'/api/v1/tasks/{self.task.pk}/cancel')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error']['code'], 'PERMISSION_DENIED')

    def test_cancel_non_pending_task_returns_409(self) -> None:
        """取消已执行任务应返回 409。"""
        self.task.status = TaskStatus.CREATING
        self.task.save(update_fields=['status'])
        self.client.login(username='task-operator', password='Str0ngPassw0rd')

        response = self.client.post(f'/api/v1/tasks/{self.task.pk}/cancel')

        self.assertEqual(response.status_code, 409)

    def test_retry_failed_task(self) -> None:
        """失败任务可被重新排队。"""
        self.task.status = TaskStatus.FAILED
        self.task.finished_at = self.task.created_at
        self.task.save(update_fields=['status', 'finished_at'])
        self.client.login(username='task-operator', password='Str0ngPassw0rd')

        response = self.client.post(f'/api/v1/tasks/{self.task.pk}/retry')

        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.PENDING)
        self.assertEqual(self.task.attempt_count, 0)

    def test_retry_non_failed_task_returns_409(self) -> None:
        """重试非失败任务应返回 409。"""
        self.client.login(username='task-operator', password='Str0ngPassw0rd')

        response = self.client.post(f'/api/v1/tasks/{self.task.pk}/retry')

        self.assertEqual(response.status_code, 409)

    def test_missing_task_returns_404(self) -> None:
        """不存在的任务应返回 404。"""
        self.client.login(username='task-operator', password='Str0ngPassw0rd')

        response = self.client.post('/api/v1/tasks/00000000-0000-0000-0000-000000000000/cancel')

        self.assertEqual(response.status_code, 404)

    def test_task_list_is_ordered_by_recent(self) -> None:
        """任务列表应按创建时间倒序。"""
        other = Task.objects.create(
            type=TaskType.NODE_REFRESH,
            resource_type='node',
            resource_id='2',
            requested_by=self.viewer,
        )
        self.client.login(username='task-viewer', password='Str0ngPassw0rd')

        response = self.client.get('/api/v1/tasks')

        results = response.json()['results']
        self.assertEqual(results[0]['id'], str(other.pk))

    def test_server_side_status_filter_keeps_owner_boundary(self):
        self.client.force_login(self.operator)
        Task.objects.create(
            type='NODE_REFRESH',
            resource_type='node',
            resource_id='2',
            status='FAILED',
            requested_by=self.operator,
        )
        Task.objects.create(
            type='NODE_REFRESH',
            resource_type='node',
            resource_id='3',
            status='FAILED',
            requested_by=self.viewer,
        )
        active = self.client.get('/api/v1/tasks?status=active').json()
        self.assertEqual(active['count'], 1)
        failed = self.client.get('/api/v1/tasks?status=failed').json()
        self.assertEqual(failed['count'], 1)
        self.assertEqual(failed['results'][0]['resource_id'], '2')
