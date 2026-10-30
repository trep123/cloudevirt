import uuid
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.images.models import Image
from apps.images.uploads import execute_image_import, register_image
from apps.infrastructure.models import ManagedStoragePool
from apps.instances.tests.helpers import make_node, make_user
from common.errors import AppError


class ImagePoolPlacementTests(TestCase):
    def test_registered_image_cannot_be_attached_as_writable_system_disk(self):
        from apps.instances.disk_sources import inspect_file
        register_image({'node': self.node, 'name': 'protected-source', 'relative_path': 'source.qcow2'}, self.user)
        with self.assertRaises(AppError):
            inspect_file(self.admin, self.node, 'source.qcow2', storage_pool=self.pool.name)

    def setUp(self):
        self.user = make_user('pool-user', 'Operator')
        self.admin = make_user('pool-admin', 'Admin')
        self.node = make_node()
        self.pool = ManagedStoragePool.objects.create(
            node=self.node, name='cv-user', path='/mnt/user'
        )
        self.pool.allowed_users.add(self.user)
        self.pool.default_users.add(self.user)
        self.other = ManagedStoragePool.objects.create(
            node=self.node, name='cv-other', path='/mnt/other'
        )

    def test_registration_enforces_default_and_isolates_same_file_names(self):
        data = {'node': self.node, 'name': 'user-image', 'relative_path': 'system.qcow2'}
        image, _ = register_image(data, self.user)
        self.assertEqual(image.storage_pool_id, self.pool.pk)
        with self.assertRaises(AppError):
            register_image({**data, 'name': 'bypass', 'storage_pool': '__legacy__'}, self.user)
        other, _ = register_image(
            {**data, 'name': 'other-image', 'storage_pool': self.other.name}, self.admin
        )
        self.assertEqual(other.storage_pool_id, self.other.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Image.objects.create(
                name='duplicate',
                node=self.node,
                storage_pool=self.pool,
                relative_path='system.qcow2',
            )

    @patch('apps.images.uploads.AgentClient')
    def test_verification_keeps_original_pool_after_default_changes(self, agent):
        image, task = register_image(
            {'node': self.node, 'name': 'fixed-origin', 'relative_path': 'system.qcow2'}, self.user
        )
        self.pool.default_users.clear()
        self.other.allowed_users.add(self.user)
        self.other.default_users.add(self.user)
        agent.return_value.inspect_image.return_value = {
            'format': 'QCOW2',
            'size_bytes': 4,
            'virtual_size_bytes': 1024,
            'checksum_sha256': 'a' * 64,
        }
        execute_image_import(task)
        agent.return_value.inspect_image.assert_called_once_with(
            'system.qcow2', storage_pool=self.pool.name
        )
        image.refresh_from_db()
        self.assertEqual(image.storage_pool_id, self.pool.pk)

    def test_browser_upload_records_default_pool(self):
        self.client.force_login(self.user)
        response = self.client.post(
            '/api/v1/images/uploads',
            {
                'id': str(uuid.uuid4()),
                'name': 'pool-upload',
                'node': self.node.pk,
                'original_name': 'system.qcow2',
                'size_bytes': 4,
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(
            Image.objects.get(pk=response.json()['image_id']).storage_pool_id, self.pool.pk
        )
