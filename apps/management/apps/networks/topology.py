"""Bounded, database-backed configured topology, without per-VM agent calls."""

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.networks.models import InstanceNIC
from apps.networks.scope import networks_for
from apps.networks.serializers import NetworkSerializer
from common.permissions import CanViewNetwork, RequiresPasswordChange
from common.scope import instances_for


class NetworkTopologyView(APIView):
    permission_classes = [CanViewNetwork, RequiresPasswordChange]

    def get(self, request):
        networks = list(networks_for(request.user).order_by('node_id', 'name')[:300])
        query = (
            instances_for(request.user).select_related('node', 'image').order_by('node_id', 'name')
            if request.user.has_perm('instances.view_instance')
            else None
        )
        total = query.count() if query is not None else 0
        instances = list(query[:300]) if query is not None else []
        allowed = {n.pk for n in networks}
        interfaces = {v.pk: [] for v in instances}
        for nic in InstanceNIC.objects.filter(
            instance__in=instances, network_id__in=allowed
        ).select_related('network'):
            interfaces[nic.instance_id].append(
                {
                    'name': nic.device_id,
                    'mac': nic.mac,
                    'source': nic.network.name,
                    'type': nic.network.type,
                    'model': '',
                    'network_id': nic.network_id,
                }
            )
        return Response(
            {
                'networks': NetworkSerializer(networks, many=True).data,
                'instances': [
                    {
                        **{
                            field: getattr(v, field)
                            for field in [
                                'id',
                                'name',
                                'uuid',
                                'network_name',
                                'observed_state',
                                'observed_state_is_stale',
                                'observed_state_updated_at',
                                'operation_status',
                            ]
                        },
                        'node': v.node_id,
                        'node_name': v.node.name,
                    }
                    for v in instances
                ],
                'interfaces': interfaces,
                'truncated': total > 300,
                'total_instances': total,
            }
        )
