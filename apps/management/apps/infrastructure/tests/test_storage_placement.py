"""Pool grants, defaults and actual VM placement stay in agreement."""

from unittest.mock import patch

from django.test import TestCase

from apps.infrastructure.executors import execute_infrastructure
from apps.infrastructure.models import ManagedStoragePool
from apps.infrastructure.placement import select_storage_pool
from apps.instances.services import create_instance
from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.tasks.models import Task
from common.errors import AppError


class StoragePlacementTests(TestCase):
    def setUp(self):
        self.admin = make_user('storage-admin', 'Admin')
        self.owner = make_user('storage-owner', 'Operator')
        self.other = make_user('storage-other', 'Operator')
        self.node = make_node()
        self.image = make_image()
        self.pool = ManagedStoragePool.objects.create(
            node=self.node, name='cv-fast', path='/mnt/cloudvirt/fast', is_default=True
        )
        self.pool.allowed_users.add(self.owner)

    @staticmethod
    def listing():
        return {
            'results': [
                {
                    'name': 'cv-fast',
                    'type': 'dir',
                    'active': True,
                    'target': {'path': '/mnt/cloudvirt/fast'},
                    'capacity_bytes': 500 * 1024**3,
                    'available_bytes': 400 * 1024**3,
                }
            ]
        }

    @patch('apps.infrastructure.executors.AgentClient')
    def test_create_cross_directory_pool_persists_grants_after_agent_ack(self, client):
        client.return_value.request_json.return_value = {'name': 'cv-cross'}
        live = self.listing()['results'][0].copy()
        live['name'] = 'cv-cross'
        live['target'] = {'path': '/mnt/cloudvirt/another-disk'}
        client.return_value.get_json.return_value = {'results': [live]}
        self.client.force_login(self.admin)
        response = self.client.post(
            f'/api/v1/admin/nodes/{self.node.pk}/storage-pools/',
            {
                'name': 'cv-cross',
                'path': '/mnt/cloudvirt/another-disk',
                'assigned_user_ids': [self.other.pk],
                'default_user_ids': [self.other.pk],
                'is_default': True,
            },
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='cross-pool-1',
        )
        self.assertEqual(response.status_code, 202, response.content)
        execute_infrastructure(Task.objects.get(pk=response.json()['task_id']))
        client.return_value.request_json.assert_called_once_with(
            '/api/v1/storage-pools',
            'POST',
            {'name': 'cv-cross', 'path': '/mnt/cloudvirt/another-disk'},
        )
        pool = ManagedStoragePool.objects.get(node=self.node, name='cv-cross')
        self.assertEqual(pool.path, '/mnt/cloudvirt/another-disk')
        self.assertEqual(list(pool.allowed_users.values_list('pk', flat=True)), [self.other.pk])
        self.assertTrue(pool.is_default)
        self.assertEqual(list(pool.default_users.values_list('pk', flat=True)), [self.other.pk])
        self.pool.refresh_from_db()
        self.assertFalse(self.pool.is_default)

    @patch('apps.infrastructure.views.AgentClient')
    def test_personal_default_overrides_node_default(self, client):
        personal = ManagedStoragePool.objects.create(
            node=self.node, name='cv-personal', path='/mnt/cloudvirt/personal'
        )
        personal.allowed_users.add(self.owner)
        personal.default_users.add(self.owner)
        self.assertEqual(select_storage_pool(self.owner, self.node).pk, personal.pk)
        listing = self.listing()
        second = listing['results'][0].copy()
        second['name'] = personal.name
        second['target'] = {'path': personal.path}
        listing['results'].append(second)
        client.return_value.get_json.return_value = listing
        self.client.force_login(self.owner)
        response = self.client.get(f'/api/v1/storage-pools/available/?node={self.node.pk}')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['default'], 'cv-personal')

    @patch('apps.infrastructure.views.AgentClient')
    def test_list_only_granted_pools_and_admin_can_update_default(self, client):
        client.return_value.get_json.return_value = self.listing()
        self.client.force_login(self.owner)
        response = self.client.get(f'/api/v1/storage-pools/available/?node={self.node.pk}')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['default'], 'cv-fast')
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(f'/api/v1/storage-pools/available/?node={self.node.pk}').json()[
                'results'
            ],
            [],
        )
        self.assertEqual(
            self.client.put(
                f'/api/v1/admin/nodes/{self.node.pk}/storage-pools/cv-fast/access/',
                {'revision': 1, 'assigned_user_ids': [self.other.pk], 'is_default': True},
                content_type='application/json',
            ).status_code,
            403,
        )
        self.client.force_login(self.admin)
        response = self.client.put(
            f'/api/v1/admin/nodes/{self.node.pk}/storage-pools/cv-fast/access/',
            {'revision': 1, 'assigned_user_ids': [self.other.pk], 'is_default': True},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.pool.refresh_from_db()
        self.assertEqual(
            list(self.pool.allowed_users.values_list('pk', flat=True)), [self.other.pk]
        )
        self.assertEqual(response.json()['revision'], 2)

    @patch('apps.instances.services.AgentClient')
    def test_placement_uses_granted_pool_and_denies_other_user(self, client):
        client.return_value.get_json.return_value = self.listing()
        data = dict(
            name='storage-vm',
            node=self.node,
            image=self.image,
            vcpu=2,
            memory_mib=2048,
            disk_gib=20,
            storage_pool='cv-fast',
        )
        with self.assertRaises(AppError):
            create_instance(user=self.other, **data)
        instance, task = create_instance(user=self.owner, **data)
        self.assertEqual(instance.storage_pool_id, self.pool.pk)
        self.assertEqual(instance.creation_config['storage_pool'], 'cv-fast')
        self.assertEqual(task.payload['storage_pool'], 'cv-fast')
        self.assertEqual(instance.reservations.get().storage_pool_id, self.pool.pk)

    @patch('apps.instances.services.AgentClient')
    def test_pool_capacity_checked_independently_of_node(self, client):
        listing = self.listing()
        listing['results'][0]['available_bytes'] = 1024**3
        client.return_value.get_json.return_value = listing
        with self.assertRaises(AppError):
            create_instance(
                user=self.owner,
                name='storage-full',
                node=self.node,
                image=self.image,
                vcpu=2,
                memory_mib=2048,
                disk_gib=20,
                storage_pool='cv-fast',
            )
