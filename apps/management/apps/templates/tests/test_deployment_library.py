from django.http import Http404
from django.test import TestCase

from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.templates.models import Template, TemplateVersion
from apps.templates.versions import resolve_version


class DeploymentLibraryTests(TestCase):
    def setUp(self):
        self.admin = make_user('library-admin', 'Admin')
        self.user = make_user('library-user', 'Operator')
        self.node = make_node()
        self.image = make_image(node=self.node)
        self.config = {
            'node': self.node.pk,
            'image': self.image.pk,
            'vcpu': 2,
            'memory_mib': 2048,
            'disk_gib': 20,
            'hardware': {},
            'network_name': '',
            'additional_networks': [],
            'data_disks': [],
        }
        self.client.force_login(self.admin)

    def create(self, **overrides):
        return self.client.post(
            '/api/v1/templates/deployments',
            {'name': 'published-library', 'configuration': self.config, **overrides},
            content_type='application/json',
        )

    def test_atomic_publish_and_edit_preserves_original_snapshot(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.content)
        old = TemplateVersion.objects.get(pk=response.json()['id'])
        changed = self.client.patch(
            f'/api/v1/template-versions/{old.pk}',
            {'configuration': {**self.config, 'vcpu': 4}},
            content_type='application/json',
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        old.refresh_from_db()
        self.assertTrue(old.is_deleted)
        self.assertEqual(old.configuration['vcpu'], 2)
        self.assertEqual(changed.json()['version'], 2)
        self.assertEqual(changed.json()['configuration']['vcpu'], 4)
        rows = self.client.get('/api/v1/templates/deployments').json()['results']
        self.assertEqual([v['id'] for v in rows], [changed.json()['id']])
        with self.assertRaises(Http404):
            resolve_version({'template_version': old.pk}, self.user)
        self.assertEqual(
            self.client.post(
                f'/api/v1/template-versions/{old.pk}/publish', {}, content_type='application/json'
            ).status_code,
            404,
        )

    def test_invalid_creation_and_edit_roll_back_all_metadata(self):
        for config in [None, [], {**self.config, 'image': 999999}]:
            response = self.create(configuration=config)
            self.assertEqual(response.status_code, 400, response.content)
            self.assertEqual(Template.objects.count(), 0)
        valid = self.create().json()
        response = self.client.patch(
            f'/api/v1/template-versions/{valid["id"]}',
            {'name': 'should-rollback', 'configuration': {**self.config, 'image': 999999}},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(Template.objects.get().name, 'published-library')
        self.assertEqual(TemplateVersion.objects.count(), 1)
        self.assertFalse(TemplateVersion.objects.get().is_deleted)

    def test_delete_keeps_snapshot_but_blocks_future_deployments(self):
        version = self.create().json()
        response = self.client.delete(f'/api/v1/template-versions/{version["id"]}')
        self.assertEqual(response.status_code, 204)
        self.assertTrue(TemplateVersion.objects.get().is_deleted)
        self.assertEqual(self.client.get('/api/v1/templates/deployments').json()['results'], [])
        with self.assertRaises(Http404):
            resolve_version({'template_version': version['id']}, self.user)

    def test_ordinary_user_cannot_create_edit_or_delete(self):
        version = self.create(is_public=False, assigned_users=[self.user.pk]).json()
        admin_row = self.client.get('/api/v1/templates/deployments').json()['results'][0]
        self.assertEqual(admin_row['assigned_users'], [self.user.pk])
        self.client.force_login(self.user)
        user_row = self.client.get('/api/v1/templates/deployments').json()['results'][0]
        self.assertNotIn('assigned_users', user_row)
        self.assertEqual(self.create().status_code, 403)
        self.assertEqual(
            self.client.patch(
                f'/api/v1/template-versions/{version["id"]}',
                {'name': 'forbidden'},
                content_type='application/json',
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(f'/api/v1/template-versions/{version["id"]}').status_code, 403
        )
        self.assertEqual(len(self.client.get('/api/v1/templates/deployments').json()['results']), 1)
