from django.test import TestCase

from apps.infrastructure.models import StorageBackend
from apps.instances.tests.helpers import make_user
from apps.tasks.models import Task


class StorageContractTests(TestCase):
    def setUp(self):
        self.admin = make_user('storage-contract-admin', 'Admin')
        self.user = make_user('storage-contract-user', 'Viewer')
        self.client.force_login(self.admin)
        self.body = {
            'name': 'minio-backups',
            'driver': 's3',
            'usage': 'backups',
            'configuration': {'endpoint': 'https://minio.example.com', 'bucket': 'backups'},
            'credential_ref': 'secret://minio-backup',
        }

    def create(self, body=None):
        return self.client.post(
            '/api/v1/admin/storage-backends/', body or self.body, content_type='application/json'
        )

    def test_catalog_never_advertises_unimplemented_drivers(self):
        result = self.client.get('/api/v1/admin/storage-drivers/').json()
        self.assertEqual(result['contract_version'], 1)
        self.assertEqual({r['code'] for r in result['results']}, {'directory', 'ceph_rbd', 's3'})
        self.assertTrue(
            all(not r['available'] and not r['capabilities'] for r in result['results'])
        )

    def test_draft_lifecycle_and_probe_fail_closed(self):
        result = self.create()
        self.assertEqual(result.status_code, 201, result.content)
        row = result.json()
        self.assertFalse(row['available'])
        self.assertEqual(row['state'], 'draft')
        path = f'/api/v1/admin/storage-backends/{row["id"]}/'
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/admin/storage-backends/').json()['count'], 1)
        self.assertEqual(self.client.post(path + 'probe/').status_code, 409)
        self.assertFalse(Task.objects.exists())
        updated = self.client.put(
            path, self.body | {'revision': 1, 'name': 'renamed'}, content_type='application/json'
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.json()['revision'], 2)
        self.assertEqual(
            self.client.put(
                path, self.body | {'revision': 1}, content_type='application/json'
            ).status_code,
            409,
        )
        self.assertEqual(self.client.delete(path).status_code, 204)
        self.assertFalse(StorageBackend.objects.exists())

    def test_objects_cannot_be_selected_for_vm_disks_or_enabled(self):
        self.assertEqual(self.create(self.body | {'usage': 'vm_disks'}).status_code, 400)
        self.assertEqual(self.create(self.body | {'enabled': True}).status_code, 400)
        self.assertFalse(StorageBackend.objects.exists())

    def test_secret_values_and_credential_urls_are_rejected(self):
        for key in ['access_key', 'secret_key', 'password', 'token']:
            configuration = self.body['configuration'] | {key: 'never-store-this'}
            self.assertEqual(
                self.create(self.body | {'configuration': configuration}).status_code, 400
            )
        self.assertEqual(self.create(self.body | {'credential_ref': 'plaintext'}).status_code, 400)
        configuration = self.body['configuration'] | {
            'endpoint': 'https://user:pass@minio.example.com'
        }
        self.assertEqual(self.create(self.body | {'configuration': configuration}).status_code, 400)
        self.assertFalse(StorageBackend.objects.exists())

    def test_directory_and_rbd_configuration_schemas(self):
        for driver, config in [
            ('directory', {'path': '/var/lib/cloudvirt/data'}),
            ('ceph_rbd', {'monitors': ['10.0.0.2:3300'], 'pool': 'vms', 'user': 'cloudvirt'}),
        ]:
            result = self.create(
                {'name': driver, 'driver': driver, 'usage': 'vm_disks', 'configuration': config}
            )
            self.assertEqual(result.status_code, 201, result.content)
        result = self.create(
            {
                'name': 'bad-path',
                'driver': 'directory',
                'usage': 'vm_disks',
                'configuration': {'path': '/data/../etc'},
            }
        )
        self.assertEqual(result.status_code, 400)

    def test_ordinary_user_cannot_read_or_mutate_profiles(self):
        pk = self.create().json()['id']
        self.client.force_login(self.user)
        path = f'/api/v1/admin/storage-backends/{pk}/'
        for response in [
            self.client.get('/api/v1/admin/storage-drivers/'),
            self.client.get('/api/v1/admin/storage-backends/'),
            self.client.get(path),
            self.create(),
            self.client.delete(path),
            self.client.post(path + 'probe/'),
            self.client.put(path, self.body, content_type='application/json'),
        ]:
            self.assertEqual(response.status_code, 403)
        self.assertEqual(StorageBackend.objects.count(), 1)
