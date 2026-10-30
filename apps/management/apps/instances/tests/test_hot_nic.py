from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.instances.tests import test_device_management as helpers
from apps.networks.models import InstanceNIC, Network
from apps.tasks.models import Task


class HotNICTests(TestCase):
    setUp = helpers.DeviceManagementTests.setUp
    post = helpers.DeviceManagementTests.post
    run_task = helpers.DeviceManagementTests.run_task

    def running(self):
        self.vm.observed_state = 'RUNNING'
        self.vm.observed_state_updated_at = timezone.now()
        self.vm.save()

    def test_hot_add_is_idempotent_and_registration_waits_for_verified_result(self):
        self.running()
        net = Network.objects.create(name='hot-net')
        with patch('apps.nodes.client.AgentClient.get_json', return_value={'nic_hotplug': True}):
            for _ in range(2):
                response = self.client.post(
                    self.url,
                    {
                        'operation': 'nic-add',
                        'network_name': net.name,
                        'model': 'virtio',
                        'live': True,
                    },
                    content_type='application/json',
                    HTTP_IDEMPOTENCY_KEY='hot-key',
                )
                self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(Task.objects.count(), 1)
        self.assertFalse(InstanceNIC.objects.filter(instance=self.vm).exists())
        change = Task.objects.get().payload['change']
        self.assertTrue(change['live'])
        self.run_task(
            {
                'uuid': str(self.vm.uuid),
                'nics': [{'mac': change['mac'], 'model': 'virtio', 'source': net.name}],
            }
        )
        self.assertEqual(InstanceNIC.objects.get(instance=self.vm).network_id, net.pk)

    def test_ordinary_user_stale_and_other_hot_operations_are_rejected(self):
        self.running()
        net = Network.objects.create(name='hot-denied')
        self.client.force_login(self.owner)
        self.assertEqual(
            self.post(
                operation='nic-add', network_name=net.name, model='virtio', live=True
            ).status_code,
            403,
        )
        self.client.force_login(self.admin)
        self.assertEqual(
            self.post(operation='compute', vcpu=2, memory_mib=1024, live=True).status_code, 400
        )
        self.vm.observed_state_is_stale = True
        self.vm.save()
        self.assertEqual(
            self.post(
                operation='nic-add', network_name=net.name, model='virtio', live=True
            ).status_code,
            409,
        )

    def test_protected_duplicate_and_unsupported_node_are_rejected(self):
        self.running()
        net = Network.objects.create(name='management-hot', is_management=True)
        with patch('apps.nodes.client.AgentClient.get_json', return_value={'nic_hotplug': True}):
            self.assertIn(
                self.post(
                    operation='nic-add', network_name=net.name, model='virtio', live=True
                ).status_code,
                [400, 409],
            )
            net.is_management = False
            net.save()
            InstanceNIC.objects.create(
                instance=self.vm, network=net, device_id='ethx', mac='02:11:22:33:44:55'
            )
            self.assertEqual(
                self.post(
                    operation='nic-add', network_name=net.name, model='virtio', live=True
                ).status_code,
                409,
            )
        with patch('apps.nodes.client.AgentClient.get_json', return_value={}):
            self.assertEqual(
                self.post(
                    operation='nic-add', network_name=net.name, model='virtio', live=True
                ).status_code,
                409,
            )
