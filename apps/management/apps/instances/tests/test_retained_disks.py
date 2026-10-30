from unittest.mock import patch

from django.test import TestCase

from apps.instances.disk_cleanup import execute_disk_delete
from apps.instances.models import Disk, Instance
from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.tasks.models import Task
from common.errors import AppError


class RetainedDiskTests(TestCase):
    def setUp(self):
        self.owner = make_user('disk-owner', 'Operator')
        self.other = make_user('disk-other', 'Operator')
        node = make_node()
        image = make_image(node=node)
        self.instance = Instance.objects.create(
            name='removed-vm',
            node=node,
            image=image,
            created_by=self.owner,
            vcpu=2,
            memory_mib=1024,
            disk_gib=10,
            is_deleted=True,
        )
        self.disk = Disk.objects.create(
            instance=self.instance,
            name='retained.qcow2',
            relative_path='retained.qcow2',
            size_gib=10,
            status='READY',
            is_orphan=True,
        )
        self.client.force_login(self.owner)

    def delete(self, key='same-request'):
        return self.client.delete(f'/api/v1/disks/{self.disk.pk}', HTTP_IDEMPOTENCY_KEY=key)

    def test_retained_disks_visible_only_to_owner(self):
        result = self.client.get('/api/v1/disks?retained=true')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['count'], 1)
        self.assertTrue(result.json()['results'][0]['can_delete'])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/api/v1/disks').json()['count'], 0)
        self.assertEqual(self.delete().status_code, 404)

    def test_attached_disk_cannot_be_deleted(self):
        self.instance.is_deleted = False
        self.instance.save()
        self.assertEqual(self.delete().status_code, 409)
        self.assertFalse(Task.objects.exists())

    def test_duplicate_request_reuses_task(self):
        first = self.delete()
        self.assertEqual(first.status_code, 202, first.content)
        self.assertEqual(first.json()['task_id'], self.delete().json()['task_id'])
        self.assertEqual(Task.objects.count(), 1)

    @patch('apps.instances.disk_cleanup.AgentClient')
    def test_only_agent_ack_marks_deleted(self, client):
        self.delete()
        task = Task.objects.get()
        client.return_value.request_json.return_value = {
            'deleted': False,
            'relative_path': self.disk.relative_path,
        }
        with self.assertRaises(AppError):
            execute_disk_delete(task)
        self.disk.refresh_from_db()
        self.assertEqual(self.disk.status, 'READY')
        client.return_value.request_json.return_value = {
            'deleted': True,
            'relative_path': self.disk.relative_path,
        }
        execute_disk_delete(task)
        self.disk.refresh_from_db()
        self.instance.refresh_from_db()
        self.assertEqual(self.disk.status, 'DELETED')
        self.assertTrue(self.instance.disks_deleted)
        from common.quota import quota_for

        self.assertEqual(quota_for(self.owner)['used']['disk_gib'], 0)

    @patch('apps.instances.disk_cleanup.AgentClient')
    def test_revoked_permission_stops_worker_before_rpc(self, client):
        self.delete()
        task = Task.objects.get()
        self.owner.groups.clear()
        with self.assertRaises(AppError):
            execute_disk_delete(task)
        client.return_value.request_json.assert_not_called()

    def test_deleted_disks_hidden_unless_history_requested(self):
        self.disk.status = 'DELETED'
        self.disk.is_orphan = False
        self.disk.save()
        self.assertEqual(self.client.get('/api/v1/disks').json()['count'], 0)
        self.assertEqual(self.client.get('/api/v1/disks?retained=true').json()['count'], 0)
        history = self.client.get('/api/v1/disks?status=DELETED').json()
        self.assertEqual(history['count'], 1)
        self.assertFalse(history['results'][0]['can_delete'])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/api/v1/disks?status=DELETED').json()['count'], 0)

    def test_viewer_can_delete_own_retained_disk_only(self):
        viewer = make_user('disk-viewer', 'Viewer')
        self.instance.created_by = viewer
        self.instance.save()
        self.client.force_login(viewer)
        self.assertTrue(self.client.get('/api/v1/disks').json()['results'][0]['can_delete'])
        self.assertEqual(self.delete().status_code, 202)
        self.client.force_login(self.other)
        self.assertEqual(self.delete('other-request').status_code, 404)
