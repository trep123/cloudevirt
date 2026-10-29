import base64

from django.db import transaction
from django.test import TestCase

from apps.instances.services import create_instance
from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.networks.models import IPLease, IPPool, Network
from common.errors import AppError


class StaticProvisioningTests(TestCase):
    def setUp(self):
        self.user = make_user('static-admin', 'Admin')
        self.node = make_node()
        self.image = make_image(node=self.node, supports_cloud_init=True)
        self.network = Network.objects.create(
            name='static-net',
            type='BRIDGE',
            bridge='br-test',
            subnet='10.22.0.0/24',
            gateway='10.22.0.1',
        )
        self.pool = IPPool.objects.create(
            name='single',
            network=self.network,
            first_ip='10.22.0.10',
            last_ip='10.22.0.10',
            gateway='10.22.0.1',
            dns_servers=['10.22.0.1'],
        )
        blob = (11).to_bytes(4, 'big') + b'ssh-ed25519' + (32).to_bytes(4, 'big') + b'x' * 32
        self.initialization = {
            'username': 'cloudvirt',
            'ssh_public_keys': ['ssh-ed25519 ' + base64.b64encode(blob).decode()],
        }

    def create(self, name):
        return create_instance(
            user=self.user,
            name=name,
            node=self.node,
            image=self.image,
            vcpu=1,
            memory_mib=512,
            disk_gib=20,
            network_name=self.network.name,
            initialization=self.initialization,
            static_networks={self.network.name: {'pool': self.pool.pk}},
        )

    def test_lease_and_mac_snapshot_match_and_pool_exhaustion_rolls_back(self):
        instance, task = self.create('static-first')
        lease = IPLease.objects.get()
        config = instance.creation_config
        self.assertEqual(config['primary_mac'], lease.nic.mac)
        self.assertEqual(config['guest_networks'][0]['address'], '10.22.0.10/24')
        self.assertFalse(config['guest_networks'][0]['dhcp4'])
        self.assertEqual(task.payload['creation_config']['primary_mac'], lease.nic.mac)
        with self.assertRaises(AppError), transaction.atomic():
            self.create('static-second')
        self.assertEqual(IPLease.objects.filter(active=True).count(), 1)
        self.assertEqual(self.node.instances.count(), 1)
