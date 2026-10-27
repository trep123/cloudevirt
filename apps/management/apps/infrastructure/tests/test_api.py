"""Resource scope, capacity and irreversible-operation boundaries (requires PostgreSQL)."""

from unittest.mock import patch

from django.test import TestCase

from apps.infrastructure.models import (
    Cluster,
    ClusterNode,
    ConsoleConfiguration,
    PoolInstance,
    ResourcePool,
)
from apps.instances.models import Instance
from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.tasks.models import Task
from common.quota import quota_for


class InfrastructureAPITests(TestCase):
    def setUp(self):
        self.admin = make_user('infra-admin', 'Admin')
        self.owner = make_user('infra-owner', 'Operator')
        self.other = make_user('infra-other', 'Operator')
        self.node = make_node()
        self.cluster = Cluster.objects.create(name='cluster-a')
        ClusterNode.objects.create(cluster=self.cluster, node=self.node)
        self.vm = Instance.objects.create(
            name='infra-vm',
            libvirt_domain_name='cv-infra-vm',
            node=self.node,
            image=make_image(),
            created_by=self.owner,
            vcpu=2,
            memory_mib=2048,
            disk_gib=20,
            observed_state='SHUTOFF',
            observed_state_is_stale=False,
        )
        self.client.force_login(self.admin)

    def post(self, path, data, **headers):
        return self.client.post('/api/v1/' + path, data, content_type='application/json', **headers)

    def test_administrative_pages_deny_ordinary_user(self):
        self.client.force_login(self.owner)
        for path in [
            'admin/clusters/',
            'admin/resource-pools/',
            'admin/settings/',
            f'admin/nodes/{self.node.pk}/storage-pools/',
        ]:
            self.assertEqual(self.client.get('/api/v1/' + path).status_code, 403)

    @patch('apps.infrastructure.views.AgentClient')
    def test_snapshot_read_does_not_leak_other_users_vm(self, agent):
        self.client.force_login(self.other)
        response = self.client.get(f'/api/v1/snapshots/instances/{self.vm.pk}/')
        self.assertEqual(response.status_code, 404)
        agent.assert_not_called()

    def test_node_cannot_belong_to_two_clusters(self):
        response = self.post('admin/clusters/', {'name': 'cluster-b', 'node_ids': [self.node.pk]})
        self.assertEqual(response.status_code, 409)
        self.assertFalse(Cluster.objects.filter(name='cluster-b').exists())

    def pool_data(self):
        return {
            'name': 'pool-a',
            'cluster_id': self.cluster.pk,
            'vcpu_limit': 4,
            'memory_mib_limit': 4096,
            'disk_gib_limit': 50,
            'instance_ids': [self.vm.pk],
        }

    def test_resource_pool_capacity_is_enforced(self):
        data = self.pool_data()
        data['vcpu_limit'] = 1
        self.assertEqual(self.post('admin/resource-pools/', data).status_code, 409)
        self.assertFalse(ResourcePool.objects.exists())

    def test_cluster_node_in_use_by_resource_pool_cannot_be_removed(self):
        self.assertEqual(self.post('admin/resource-pools/', self.pool_data()).status_code, 201)
        response = self.post(
            f'admin/clusters/{self.cluster.pk}/', {'name': 'cluster-a', 'node_ids': []}
        )
        self.assertEqual(response.status_code, 409)
        self.assertTrue(ClusterNode.objects.filter(node=self.node).exists())
        self.assertTrue(PoolInstance.objects.filter(instance=self.vm).exists())

    def test_settings_revision_conflict_and_live_quota(self):
        payload = {
            'revision': 0,
            'quota': {'instances': 3, 'vcpu': 4, 'memory_mib': 4096, 'disk_gib': 100},
            'storage_warning_percent': 75,
            'storage_critical_percent': 92,
        }
        response = self.client.put(
            '/api/v1/admin/settings/', payload, content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(quota_for(self.owner)['limits']['instances'], 3)
        self.assertEqual(
            self.client.put(
                '/api/v1/admin/settings/', payload, content_type='application/json'
            ).status_code,
            409,
        )
        self.assertEqual(ConsoleConfiguration.objects.get(pk=1).revision, 1)

    def test_threshold_order_is_validated(self):
        payload = {
            'revision': 0,
            'quota': {'instances': 3, 'vcpu': 4, 'memory_mib': 4096, 'disk_gib': 100},
            'storage_warning_percent': 95,
            'storage_critical_percent': 90,
        }
        self.assertEqual(
            self.client.put(
                '/api/v1/admin/settings/', payload, content_type='application/json'
            ).status_code,
            400,
        )
        self.assertFalse(ConsoleConfiguration.objects.exists())

    def test_snapshot_submission_is_idempotent_and_requires_shutdown(self):
        path = f'snapshots/instances/{self.vm.pk}/'
        headers = {'HTTP_IDEMPOTENCY_KEY': 'snap-key'}
        body = {'action': 'create', 'name': 'cv-test-snapshot'}
        first, second = self.post(path, body, **headers), self.post(path, body, **headers)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.json()['task_id'], first.json()['task_id'])
        self.assertEqual(Task.objects.filter(type='INSTANCE_SNAPSHOT').count(), 1)
        self.assertEqual(
            self.post(
                path, {'action': 'delete', 'name': 'cv-test-snapshot'}, **headers
            ).status_code,
            409,
        )
        self.vm.observed_state = 'RUNNING'
        self.vm.save()
        self.assertEqual(
            self.post(path, body, HTTP_IDEMPOTENCY_KEY='different-key').status_code, 409
        )

    def test_snapshot_write_requires_admin_even_for_owner(self):
        self.client.force_login(self.owner)
        self.assertEqual(
            self.post(
                f'snapshots/instances/{self.vm.pk}/',
                {'action': 'create'},
                HTTP_IDEMPOTENCY_KEY='owner-key',
            ).status_code,
            403,
        )

    def test_failed_snapshot_cannot_be_replayed_from_task_center(self):
        task = Task.objects.create(
            type='INSTANCE_SNAPSHOT',
            status='FAILED',
            resource_type='instance',
            resource_id=str(self.vm.pk),
            requested_by=self.admin,
        )
        self.assertEqual(self.post(f'tasks/{task.pk}/retry', {}).status_code, 409)
