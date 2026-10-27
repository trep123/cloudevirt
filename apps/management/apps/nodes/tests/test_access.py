"""节点对象级授权测试。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.accounts.roles import sync_role_permissions
from apps.nodes.access import accessible_node_ids, user_can_access
from apps.nodes.models import Node, NodeAccess, NodePermission, NodeStatus


class NodeAccessTests(TestCase):
    """授权判定与 API。"""

    def setUp(self) -> None:
        """创建节点与各角色用户。"""
        sync_role_permissions()
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(username='na-admin', password='Str0ngPassw0rd')
        self.admin.groups.add(Group.objects.get(name='Admin'))
        self.operator = user_model.objects.create_user(
            username='na-operator', password='Str0ngPassw0rd'
        )
        self.operator.groups.add(Group.objects.get(name='Operator'))
        self.node_a = Node.objects.create(
            name='node-a', endpoint='http://127.0.0.1:9101', status=NodeStatus.ONLINE
        )
        self.node_b = Node.objects.create(
            name='node-b', endpoint='http://127.0.0.1:9102', status=NodeStatus.ONLINE
        )

    def test_admin_has_all_access(self) -> None:
        """Admin 默认对全部节点有权限。"""
        self.assertTrue(user_can_access(self.admin, self.node_a, NodePermission.OPERATE))
        self.assertEqual(
            accessible_node_ids(self.admin),
            {self.node_a.pk, self.node_b.pk},
        )

    def test_no_explicit_rules_allows_all(self) -> None:
        """没有任何授权记录时默认放行（向后兼容）。"""
        self.assertTrue(user_can_access(self.operator, self.node_a, NodePermission.OPERATE))
        self.assertEqual(
            accessible_node_ids(self.operator),
            {self.node_a.pk, self.node_b.pk},
        )

    def test_explicit_rule_restricts_to_granted_nodes(self) -> None:
        """存在显式授权后，只有命中授权的节点可访问。"""
        NodeAccess.objects.create(
            node=self.node_a, user=self.operator, permission=NodePermission.OPERATE
        )

        self.assertTrue(user_can_access(self.operator, self.node_a, NodePermission.OPERATE))
        self.assertFalse(user_can_access(self.operator, self.node_b, NodePermission.OPERATE))
        self.assertEqual(accessible_node_ids(self.operator), {self.node_a.pk})

    def test_group_grant_works(self) -> None:
        """用户组授权生效。"""
        NodeAccess.objects.create(
            node=self.node_b,
            group=Group.objects.get(name='Operator'),
            permission=NodePermission.OPERATE,
        )

        self.assertTrue(user_can_access(self.operator, self.node_b, NodePermission.OPERATE))
        self.assertFalse(user_can_access(self.operator, self.node_a, NodePermission.OPERATE))

    def test_access_api_requires_admin(self) -> None:
        """授权接口：Operator 可查、不可建；Admin 可建可删。"""

        # Operator 查询
        self.client.login(username='na-operator', password='Str0ngPassw0rd')
        response = self.client.get('/api/v1/node-access?node=%d' % self.node_a.pk)
        self.assertEqual(response.status_code, 200)

        # Operator 创建 → 403
        response = self.client.post(
            '/api/v1/node-access',
            {'node': self.node_a.pk, 'user': self.operator.pk, 'permission': 'OPERATE'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

        # Admin 创建
        self.client.login(username='na-admin', password='Str0ngPassw0rd')
        response = self.client.post(
            '/api/v1/node-access',
            {'node': self.node_a.pk, 'user': self.operator.pk, 'permission': 'OPERATE'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

        # Admin 删除
        access_id = response.json()['id']
        delete = self.client.delete(f'/api/v1/node-access/{access_id}')
        self.assertEqual(delete.status_code, 204)

    def test_access_requires_target(self) -> None:
        """user 与 group 至少指定一个。"""
        self.client.login(username='na-admin', password='Str0ngPassw0rd')
        response = self.client.post(
            '/api/v1/node-access',
            {'node': self.node_a.pk, 'permission': 'OPERATE'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
