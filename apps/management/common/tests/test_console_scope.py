"""Console ownership, aggregate privacy and retry boundaries."""

from django.test import TestCase

from apps.instances.services import create_instance
from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.nodes.access import accessible_node_ids
from apps.nodes.models import NodeAccess, NodePermission
from apps.tasks.models import TaskStatus
from common.errors import AppError


class ConsoleScopeTests(TestCase):
    def setUp(self):
        self.owner = make_user('console-owner', 'Operator')
        self.other = make_user('console-other', 'Operator')
        self.admin = make_user('console-admin', 'Admin')
        self.node = make_node()
        self.image = make_image()
        self.instance, self.task = create_instance(
            user=self.owner,
            name='vm-owned',
            node=self.node,
            image=self.image,
            vcpu=1,
            memory_mib=512,
            disk_gib=5,
            idempotency_key='create-owned',
        )

    def test_other_user_cannot_retrieve_or_operate_instance(self):
        self.client.force_login(self.other)
        for suffix in ['', '/console', '/addresses', '/interfaces']:
            response = self.client.get(f'/api/v1/instances/{self.instance.pk}{suffix}')
            self.assertEqual(response.status_code, 404)
        response = self.client.post(f'/api/v1/instances/{self.instance.pk}/start')
        self.assertEqual(response.status_code, 404)
        response = self.client.delete(f'/api/v1/instances/{self.instance.pk}')
        self.assertEqual(response.status_code, 404)

    def test_other_user_cannot_read_or_cancel_task(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/api/v1/tasks').json()['count'], 0)
        self.assertEqual(self.client.get(f'/api/v1/tasks/{self.task.pk}').status_code, 404)
        self.assertEqual(self.client.post(f'/api/v1/tasks/{self.task.pk}/cancel').status_code, 404)

    def test_user_dashboard_excludes_others_and_global_metrics(self):
        self.client.force_login(self.other)
        response = self.client.get('/api/v1/console/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['instances']['total'], 0)
        self.assertIsNone(response.json()['memory_percent'])
        self.assertEqual(response.json()['tasks'], [])
        self.assertEqual(self.client.get('/api/v1/console/roles').status_code, 403)
        self.assertEqual(self.client.get('/api/v1/monitoring/overview').status_code, 403)

    def test_admin_can_retrieve_instance(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(f'/api/v1/instances/{self.instance.pk}').status_code, 200)

    def test_global_acl_does_not_grant_unlisted_user_all_nodes(self):
        NodeAccess.objects.create(
            node=self.node, user=self.owner, permission=NodePermission.OPERATE
        )
        self.assertEqual(accessible_node_ids(self.other), set())

    def test_console_namespaces_enforce_server_identity(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/api/v1/admin/vms/').status_code, 403)
        self.assertEqual(self.client.get('/api/v1/operator/vms/').json()['count'], 0)
        self.assertEqual(
            self.client.get(f'/api/v1/operator/vms/{self.instance.pk}/console/').status_code,
            404,
        )
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/api/v1/admin/vms/').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/operator/vms/').status_code, 403)

    def test_completed_create_with_same_key_returns_original(self):
        self.task.status = TaskStatus.SUCCEEDED
        self.task.save(update_fields=['status'])
        instance, task = create_instance(
            user=self.owner,
            name='vm-owned',
            node=self.node,
            image=self.image,
            vcpu=1,
            memory_mib=512,
            disk_gib=5,
            idempotency_key='create-owned',
        )
        self.assertEqual(instance.pk, self.instance.pk)
        self.assertEqual(task.pk, self.task.pk)

    def test_create_key_cannot_be_reused_for_different_spec(self):
        with self.assertRaises(AppError):
            create_instance(
                user=self.owner,
                name='vm-different',
                node=self.node,
                image=self.image,
                vcpu=2,
                memory_mib=512,
                disk_gib=5,
                idempotency_key='create-owned',
            )
