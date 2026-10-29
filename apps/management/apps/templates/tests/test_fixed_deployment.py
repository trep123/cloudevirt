from types import SimpleNamespace

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.instances.serializers import InstanceCreateSerializer
from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.networks.models import Network
from apps.templates.models import Template, TemplateVersion
from apps.templates.versions import resolve_version


class FixedDeploymentTests(TestCase):
    def setUp(self):
        self.user = make_user('fixed-user', 'Admin')
        self.node = make_node()
        self.image = make_image(node=self.node)
        self.template = Template.objects.create(
            name='fixed', vcpu=2, memory_mib=2048, disk_gib=20, is_public=True
        )
        self.config = {
            'node': self.node.pk,
            'image': self.image.pk,
            'vcpu': 2,
            'memory_mib': 2048,
            'disk_gib': 20,
            'hardware': {'nic_model': 'virtio'},
            'data_disks': [10],
            'additional_networks': ['old-extra'],
        }
        self.version = TemplateVersion.objects.create(
            template=self.template,
            version=1,
            published=True,
            configuration=self.config,
            image_checksum=self.image.checksum_sha256,
        )

    def test_only_name_and_network_bindings_are_needed(self):
        Network.objects.create(name='new-extra')
        s = InstanceCreateSerializer(
            data={
                'template_version': self.version.pk,
                'name': 'vm-fixed',
                'additional_networks': ['new-extra'],
            },
            context={'request': SimpleNamespace(user=self.user)},
        )
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data['node'], self.node)
        self.assertEqual(s.validated_data['data_disks'], [10])
        self.assertEqual(s.validated_data['additional_networks'], ['new-extra'])

    def test_direct_hardware_overrides_are_rejected(self):
        for field, value in [
            ('vcpu', 4),
            ('memory_mib', 8192),
            ('disk_gib', 99),
            ('node', 999),
            ('hardware', {}),
            ('data_disks', []),
            ('autostart', True),
        ]:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                resolve_version({'template_version': self.version.pk, field: value}, self.user)

    def test_ordinary_user_can_rebind_template_nics_without_editing_hardware(self):
        viewer = make_user('fixed-viewer', 'Viewer')
        Network.objects.create(name='viewer-extra')
        s = InstanceCreateSerializer(
            data={
                'template_version': self.version.pk,
                'name': 'vm-viewer',
                'additional_networks': ['viewer-extra'],
            },
            context={'request': SimpleNamespace(user=viewer)},
        )
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data['hardware'], self.config['hardware'])

    def test_nic_count_and_malformed_bindings_are_rejected(self):
        for value in [None, 1, [], ['a', 'b']]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                resolve_version(
                    {'template_version': self.version.pk, 'additional_networks': value}, self.user
                )
