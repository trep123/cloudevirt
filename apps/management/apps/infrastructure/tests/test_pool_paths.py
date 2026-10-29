from django.test import TestCase

from apps.instances.tests.helpers import make_node, make_user
from apps.tasks.models import Task


class PoolPathTests(TestCase):
    def setUp(self):
        self.admin = make_user('pool-path-admin', 'Admin')
        self.node = make_node()
        self.client.force_login(self.admin)

    def post(self, path):
        return self.client.post(
            f'/api/v1/admin/nodes/{self.node.pk}/storage-pools/',
            {'name': 'cv-explicit', 'path': path},
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='pool-path',
        )

    def test_explicit_directory_is_preserved_in_task(self):
        r = self.post('/var/lib/cloudvirt/disks/nested/custom')
        self.assertEqual(r.status_code, 202, r.content)
        self.assertEqual(
            Task.objects.get().payload['path'], '/var/lib/cloudvirt/disks/nested/custom'
        )

    def test_relative_and_traversal_directories_are_rejected(self):
        for path in ['relative/dir', '/allowed/../etc', '/path\x00invalid']:
            with self.subTest(path=path):
                self.assertEqual(self.post(path).status_code, 400)
        self.assertFalse(Task.objects.exists())

    def test_ordinary_user_cannot_create_storage_pool(self):
        self.client.force_login(make_user('pool-path-viewer', 'Viewer'))
        self.assertEqual(self.post('/var/lib/cloudvirt/disks/custom').status_code, 403)
