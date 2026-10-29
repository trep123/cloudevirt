from django.contrib.auth.models import Permission
from django.http import Http404
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.templates.models import Template, TemplateVersion
from apps.templates.versions import resolve_version


class TemplateAssignmentTests(TestCase):
    def test_assigned_user_can_deploy_but_cannot_inject_hardware(self):
        from apps.instances.models import Instance

        self.client.force_login(self.user)
        payload = {
            'name': 'assigned-deploy',
            'node': self.node.pk,
            'template_version': self.version.pk,
        }
        response = self.client.post(
            '/api/v1/operator/vms/', payload, content_type='application/json'
        )
        self.assertEqual(response.status_code, 202, response.content)
        vm = Instance.objects.get(name='assigned-deploy')
        self.assertEqual(vm.disks.get(role='DATA').bus, 'sata')
        self.assertEqual(vm.disks.get(role='DATA').target_dev, 'sdc')
        response = self.client.post(
            '/api/v1/operator/vms/',
            {**payload, 'name': 'injected', 'hardware': {'nic_model': 'virtio'}},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def setUp(self):
        self.admin = make_user('assigned-admin', 'Admin')
        self.user = make_user('assigned-user', 'Operator')
        self.other = make_user('assigned-other', 'Operator')
        self.node = make_node()
        self.image = make_image(node=self.node)
        self.template = Template.objects.create(
            name='assigned-template',
            vcpu=2,
            memory_mib=1024,
            disk_gib=10,
            is_public=False,
            created_by=self.admin,
        )
        self.template.assigned_users.add(self.user)
        self.version = TemplateVersion.objects.create(
            template=self.template,
            version=1,
            published=True,
            image_checksum=self.image.checksum_sha256,
            configuration={
                'image': self.image.pk,
                'vcpu': 2,
                'memory_mib': 1024,
                'disk_gib': 10,
                'hardware': {'nic_model': 'e1000e', 'data_disk_bus': 'sata'},
                'data_disks': [20],
                'additional_networks': [],
            },
        )

    def test_assignment_filters_all_read_and_resolution_paths(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(f'/api/v1/templates/{self.template.pk}').status_code, 200)
        self.assertEqual(
            self.client.get('/api/v1/templates/deployments').json()['results'][0]['id'],
            self.version.pk,
        )
        self.assertNotIn(
            'assigned_users', self.client.get(f'/api/v1/templates/{self.template.pk}').json()
        )
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f'/api/v1/templates/{self.template.pk}').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/templates/deployments').json()['results'], [])
        with self.assertRaises(Http404):
            resolve_version({'template_version': self.version.pk}, self.other)

    def test_nonadmin_cannot_override_advanced_hardware(self):
        good = resolve_version({'template_version': self.version.pk}, self.user)
        self.assertEqual(good['data_disks'], [20])
        with self.assertRaises(ValidationError):
            resolve_version({'template_version': self.version.pk, 'data_disks': [200]}, self.user)
        with self.assertRaises(ValidationError):
            resolve_version({'template_version': self.version.pk, 'hardware': {}}, self.user)

    def test_revoked_assignment_immediately_blocks_new_use(self):
        self.template.assigned_users.clear()
        with self.assertRaises(Http404):
            resolve_version({'template_version': self.version.pk}, self.user)

    def test_nonadmin_with_template_permission_cannot_edit_or_grant(self):
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label='templates', codename='add_template')
        )
        self.client.force_login(self.user)
        response = self.client.patch(
            f'/api/v1/templates/{self.template.pk}',
            {'assigned_users': [self.other.pk]},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            self.client.post(
                '/api/v1/templates',
                {'name': 'bad', 'vcpu': 2, 'memory_mib': 1024, 'disk_gib': 10},
                content_type='application/json',
            ).status_code,
            403,
        )

    def test_admin_can_assign_and_keep_public_compatibility(self):
        self.client.force_login(self.admin)
        response = self.client.patch(
            f'/api/v1/templates/{self.template.pk}',
            {'assigned_users': [self.other.pk]},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['assigned_users'], [self.other.pk])
        self.template.is_public = True
        self.template.save()
        self.assertEqual(
            resolve_version({'template_version': self.version.pk}, self.user)['template'],
            self.template.pk,
        )
