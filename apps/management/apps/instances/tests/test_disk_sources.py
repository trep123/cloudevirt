from django.test import TestCase

from apps.instances.disk_cleanup import eligible
from apps.instances.models import Disk, Instance
from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.tasks.models import Task


class DiskSourceTests(TestCase):
    def setUp(self):
        self.admin = make_user('source-admin', 'Admin')
        self.user = make_user('source-user', 'Operator')
        self.node = make_node()
        self.image = make_image(node=self.node)
        self.old = Instance.objects.create(
            name='retained-old',
            node=self.node,
            image=self.image,
            vcpu=2,
            memory_mib=1024,
            disk_gib=10,
            is_deleted=True,
            created_by=self.admin,
        )
        self.disk = Disk.objects.create(
            instance=self.old,
            name='retained.qcow2',
            relative_path='retained.qcow2',
            role='SYSTEM',
            status='DETACHED',
            is_orphan=True,
            size_gib=10,
        )
        self.payload = {
            'name': 'source-clone',
            'node': self.node.pk,
            'existing_system_disk': self.disk.pk,
            'vcpu': 2,
            'memory_mib': 1024,
            'disk_gib': 10,
            'start_after_create': False,
        }
        self.client.force_login(self.admin)

    def test_clone_uses_independent_disk_and_reserves_source_against_deletion(self):
        response = self.client.post(
            '/api/v1/instances',
            self.payload,
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='source-key',
        )
        self.assertEqual(response.status_code, 202, response.content)
        vm = Instance.objects.get(name='source-clone')
        self.assertNotEqual(vm.disks.get(role='SYSTEM').relative_path, self.disk.relative_path)
        self.assertEqual(vm.creation_config['source_disk']['id'], self.disk.pk)
        self.disk.refresh_from_db()
        self.assertEqual(self.disk.instance_id, self.old.pk)
        self.assertFalse(eligible(self.disk))
        repeated = self.client.post(
            '/api/v1/instances',
            self.payload,
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='source-key',
        )
        self.assertEqual(repeated.status_code, 202, repeated.content)
        self.assertEqual(Task.objects.filter(type='INSTANCE_CREATE').count(), 1)

    def test_user_cannot_list_or_forge_source(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/api/v1/instances/system-disk-sources').status_code, 403)
        self.assertEqual(
            self.client.post(
                '/api/v1/instances', self.payload, content_type='application/json'
            ).status_code,
            403,
        )
        self.assertFalse(Instance.objects.filter(name='source-clone').exists())

    def test_attached_deleted_wrong_node_and_shrinking_are_rejected(self):
        self.disk.is_orphan = False
        self.disk.save()
        self.assertEqual(
            self.client.post(
                '/api/v1/instances', self.payload, content_type='application/json'
            ).status_code,
            404,
        )
        self.disk.is_orphan = True
        self.disk.save()
        other = make_node(name='source-other')
        for overrides in [
            {'node': other.pk},
            {'disk_gib': 5},
            {'template_version': 999},
            {'initialization': {'username': 'test'}},
        ]:
            response = self.client.post(
                '/api/v1/instances', {**self.payload, **overrides}, content_type='application/json'
            )
            self.assertIn(response.status_code, [400, 409], response.content)
        self.disk.status = 'DELETED'
        self.disk.save()
        self.assertEqual(
            self.client.get('/api/v1/instances/system-disk-sources').json()['results'], []
        )
