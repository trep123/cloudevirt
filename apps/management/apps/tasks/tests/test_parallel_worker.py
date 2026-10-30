import io
import threading
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase

from apps.tasks.models import Task


class ParallelWorkerTests(TransactionTestCase):
    def test_independent_tasks_overlap_and_finish_exactly_once(self):
        tasks = [
            Task.objects.create(type='NODE_REFRESH', resource_type='node', resource_id=str(i))
            for i in [1, 2]
        ]
        untouched = Task.objects.create(type='NODE_REFRESH', resource_type='node', resource_id='3')
        barrier = threading.Barrier(2, timeout=10)
        threads = set()

        def execute(task):
            threads.add(threading.get_ident())
            barrier.wait()
            return {'task': str(task.pk)}

        with patch(
            'apps.tasks.management.commands.run_worker.execute_task', side_effect=execute
        ) as action:
            call_command('run_worker', concurrency=2, max_tasks=2, sleep=0.01, stdout=io.StringIO())
        untouched.refresh_from_db()
        self.assertEqual(untouched.status, 'PENDING')
        self.assertEqual(untouched.attempt_count, 0)
        self.assertEqual(action.call_count, 2)
        self.assertEqual(len(threads), 2)
        for task in tasks:
            task.refresh_from_db()
            self.assertEqual(task.status, 'SUCCEEDED')
            self.assertEqual(task.attempt_count, 1)
            self.assertEqual(task.result['task'], str(task.pk))

    def test_worker_rejects_unbounded_concurrency(self):
        with self.assertRaises(CommandError):
            call_command('run_worker', concurrency=100, once=True, stdout=io.StringIO())
