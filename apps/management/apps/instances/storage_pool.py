"""Compatibility helpers for Agent storage-pool requests."""


def agent_storage_pool(instance) -> str:
    """Return a pool name accepted by current Agents.

    Modern platform-managed pools are deliberately named ``cv-*``. Earlier
    installations recorded the node's implicit libvirt pool as ``local``;
    that pool is represented by the Agent's default disk directory and must
    therefore be sent as an empty value rather than as a managed-pool name.
    """

    if not getattr(instance, 'storage_pool_id', None):
        return ''
    name = str(instance.storage_pool.name or '')
    return name if name.startswith('cv-') else ''


def agent_storage_pool_path(instance) -> str:
    """Return the path only when an explicit managed pool is selected."""

    return instance.storage_pool.path if agent_storage_pool(instance) else ''
