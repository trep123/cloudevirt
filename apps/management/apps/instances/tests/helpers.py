"""实例测试公共构造。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from apps.accounts.roles import sync_role_permissions
from apps.images.models import Image, ImageStatus
from apps.nodes.models import Node, NodeStatus


def make_node(**kwargs) -> Node:
    """创建资源充足的在线节点。"""
    defaults = {
        'name': 'hv-1',
        'endpoint': 'http://127.0.0.1:9100',
        'status': NodeStatus.ONLINE,
        'cpu_total': 16,
        'memory_total_mib': 32768,
        'memory_available_mib': 16000,
        'storage_total_bytes': 1000 * 1024 * 1024 * 1024,
        'storage_free_bytes': 500 * 1024 * 1024 * 1024,
    }
    defaults.update(kwargs)
    return Node.objects.create(**defaults)


def make_image(**kwargs) -> Image:
    """创建可用镜像。"""
    defaults = {
        'name': 'ubuntu-24-04',
        'format': 'QCOW2',
        'relative_path': 'iso/ubuntu.qcow2',
        'size_bytes': 1024,
        'checksum_sha256': 'c' * 64,
        'status': ImageStatus.READY,
    }
    defaults.update(kwargs)
    return Image.objects.create(**defaults)


def make_user(username: str, role: str):
    """同步角色并创建指定角色的用户。"""
    sync_role_permissions()
    user = get_user_model().objects.create_user(username=username, password='Str0ngPassw0rd')
    user.groups.add(Group.objects.get(name=role))
    return user
