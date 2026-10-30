"""Network visibility for administrators and node-scoped users."""

from django.db.models import Q

from apps.accounts.administration import limit_nodes
from apps.accounts.roles import is_admin
from apps.networks.models import Network
from apps.nodes.access import accessible_node_ids


def networks_for(user):
    query = Network.objects.filter(is_deleted=False)
    if is_admin(user):
        return query
    nodes = limit_nodes(user, accessible_node_ids(user), 'networks.view_network')
    return query.filter(Q(node__isnull=True) | Q(node_id__in=nodes)).filter(
        is_management=False,
        provisioning_status='READY',
    )
