from django.test import TestCase

from apps.instances.models import Instance
from apps.instances.tests.helpers import make_image, make_node, make_user
from apps.networks.models import InstanceNIC, Network


class TopologyTests(TestCase):
    def test_all_nics_are_returned_and_other_users_instances_are_hidden(self):
        user = make_user('topology-user', 'Operator')
        other = make_user('topology-other', 'Operator')
        node = make_node()
        image = make_image(node=node)
        mine = Instance.objects.create(
            name='my-topo',
            libvirt_domain_name='cv-my-topo',
            node=node,
            image=image,
            created_by=user,
            vcpu=1,
            memory_mib=512,
            disk_gib=1,
        )
        theirs = Instance.objects.create(
            name='private-topo',
            libvirt_domain_name='cv-private-topo',
            node=node,
            image=image,
            created_by=other,
            vcpu=1,
            memory_mib=512,
            disk_gib=1,
        )
        for i in range(2):
            network = Network.objects.create(name=f'topo-{i}')
            InstanceNIC.objects.create(
                instance=mine, network=network, device_id=f'eth{i}', mac=f'02:00:00:00:01:0{i}'
            )
            InstanceNIC.objects.create(
                instance=theirs, network=network, device_id=f'eth{i}', mac=f'02:00:00:00:02:0{i}'
            )
        self.client.force_login(user)
        response = self.client.get('/api/v1/networks/topology')
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual([v['id'] for v in body['instances']], [mine.pk])
        self.assertEqual(len(body['interfaces'][str(mine.pk)]), 2)
        self.assertNotIn(str(theirs.pk), body['interfaces'])
        self.assertNotIn('creation_config', body['instances'][0])
        self.assertFalse(body['truncated'])
