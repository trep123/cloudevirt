from django.test import TestCase, override_settings

from apps.instances.services import create_instance
from apps.instances.tests.helpers import make_image, make_node, make_user
from common.errors import AppError


@override_settings(
    USER_RESOURCE_QUOTA={
        'instances': 1,
        'vcpu': 4,
        'memory_mib': 4096,
        'disk_gib': 20,
    }
)
class QuotaTests(TestCase):
    def test_pending_instance_consumes_quota(self):
        user = make_user('quota-user', 'Operator')
        node, image = make_node(), make_image()
        create_instance(
            user=user, name='vm-first', node=node, image=image, vcpu=1, memory_mib=512, disk_gib=5
        )
        with self.assertRaises(AppError) as error:
            create_instance(
                user=user,
                name='vm-second',
                node=node,
                image=image,
                vcpu=1,
                memory_mib=512,
                disk_gib=5,
            )
        self.assertIn('instances', error.exception.details['exceeded'])
