"""Shared resource boundaries for console APIs."""

from apps.accounts.roles import is_admin
from apps.instances.models import Instance
from apps.nodes.access import accessible_node_ids
from apps.tasks.models import Task


def instances_for(user):
    queryset = (
        Instance.objects.filter(is_deleted=False)
        .select_related('node', 'image')
        .prefetch_related('disks')
    )
    if is_admin(user):
        return queryset
    from apps.accounts.administration import limit_nodes

    return queryset.filter(
        created_by=user,
        node_id__in=limit_nodes(user, accessible_node_ids(user), 'instances.view_instance'),
    )


def tasks_for(user):
    queryset = Task.objects.all()
    return queryset if is_admin(user) else queryset.filter(requested_by=user)


class InstanceScopeMixin:
    def get_queryset(self):
        queryset = instances_for(self.request.user)
        search = self.request.query_params.get('search', '').strip()
        if search:
            from django.db.models import Q

            queryset = queryset.filter(Q(name__icontains=search) | Q(uuid__icontains=search))
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(observed_state=status.upper())
        node = self.request.query_params.get('node')
        if node:
            if not node.isdigit():
                return queryset.none()
            queryset = queryset.filter(node_id=node)
        return queryset.order_by('-created_at', '-pk')


class TaskScopeMixin:
    def get_queryset(self):
        return tasks_for(self.request.user)


class NodeScopeMixin:
    def get_queryset(self):
        from apps.accounts.administration import limit_nodes
        from apps.nodes.models import Node

        return Node.objects.filter(
            is_deleted=False,
            pk__in=limit_nodes(
                self.request.user, accessible_node_ids(self.request.user), 'nodes.view_node'
            ),
        ).order_by('name')
