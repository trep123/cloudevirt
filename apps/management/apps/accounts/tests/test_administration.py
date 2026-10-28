import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone
from openpyxl import Workbook

from apps.accounts.administration import invalidate_user, limit_nodes
from apps.accounts.bulk import execute_account_batch, file_bytes, parse_file
from apps.accounts.models import AccountBatch, RoleDefinition, UserProfile
from apps.accounts.roles import sync_role_permissions
from apps.nodes.models import Node
from common.errors import AppError


class AccountAdministrationTests(TestCase):
    def setUp(self):
        sync_role_permissions()
        self.admin = get_user_model().objects.create_superuser(
            'account-admin', password='Adm1nStr0ngPass'
        )
        self.client.force_login(self.admin)

    def post(self, path, data):
        return self.client.post(path, data, content_type='application/json')

    def preview(self, text, **options):
        return self.client.post(
            '/api/v1/users/batches',
            {'kind': 'import', 'file': SimpleUploadedFile('users.csv', text.encode()), **options},
        )

    def execute(self, batch_id):
        response = self.post(f'/api/v1/users/batches/{batch_id}', {})
        self.assertEqual(response.status_code, 202, response.content)
        batch = AccountBatch.objects.get(pk=batch_id)
        execute_account_batch(batch.task)
        batch.refresh_from_db()
        return batch

    def role(self, code='vm_reader', **overrides):
        return self.post(
            '/api/v1/console/roles',
            {
                'code': code,
                'display_name': '虚拟机只读',
                'permissions': ['instances.view_instance'],
                **overrides,
            },
        )

    def test_pending_import_and_idempotent_confirmation(self):
        response = self.preview(
            'username,display_name,role_codes,status\nnew-user,新用户,Viewer,pending\n'
        )
        self.assertEqual(response.status_code, 201, response.content)
        batch = self.execute(response.json()['id'])
        user = get_user_model().objects.get(username='new-user')
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(batch.state, 'SUCCEEDED')
        again = self.post(f'/api/v1/users/batches/{batch.pk}', {})
        self.assertEqual(str(batch.task_id), again.json()['task_id'])
        execute_account_batch(batch.task)
        self.assertEqual(get_user_model().objects.filter(username='new-user').count(), 1)

    def test_template_downloads_are_not_intercepted_by_content_negotiation(self):
        for format in ['csv', 'xlsx']:
            response = self.client.get('/api/v1/users/import-template', {'file_format': format})
            self.assertEqual(response.status_code, 200, response.content[:100])
            rows = parse_file(SimpleUploadedFile('template.' + format, response.content))
            self.assertEqual(rows[0]['input']['username'], 'user_example')
            self.assertEqual(response['Cache-Control'], 'no-store')

    def test_partial_mode_isolates_invalid_rows(self):
        response = self.preview(
            'username,display_name,role_codes\ngood-user,有效,Viewer\nbad-user,错误,missing-role\n'
        )
        batch = self.execute(response.json()['id'])
        self.assertEqual(batch.state, 'PARTIAL')
        self.assertTrue(get_user_model().objects.filter(username='good-user').exists())
        self.assertFalse(get_user_model().objects.filter(username='bad-user').exists())

    def test_strict_mode_rejects_invalid_preview(self):
        response = self.preview(
            'username,display_name,role_codes\ngood-user,有效,Viewer\nbad-user,错误,missing-role\n',
            strict='true',
        )
        result = self.post(f'/api/v1/users/batches/{response.json()["id"]}', {})
        self.assertEqual(result.status_code, 409, result.content)
        self.assertFalse(get_user_model().objects.filter(username='good-user').exists())

    def test_duplicate_and_privileged_columns_are_rejected(self):
        response = self.preview(
            'username,display_name,role_codes\nSame,甲,Viewer\nsame,乙,Viewer\n'
        )
        self.assertTrue(all(row['status'] == 'ERROR' for row in response.json()['preview']))
        for column in ['password', 'is_superuser', 'project_id']:
            response = self.preview(f'username,{column}\nblocked,true\n')
            self.assertEqual(response.status_code, 400, response.content)

    def test_stale_preview_does_not_overwrite_user(self):
        user = get_user_model().objects.create_user('existing', password='UsrStr0ngPassword')
        response = self.preview('username,display_name\nexisting,预览名称\n', mode='update')
        user.email = 'changed@example.test'
        user.save()
        batch = self.execute(response.json()['id'])
        self.assertEqual(batch.state, 'PARTIAL')
        self.assertEqual(user.email, get_user_model().objects.get(pk=user.pk).email)

    def test_role_change_invalidates_preview(self):
        role = self.role().json()
        response = self.preview('username,display_name,role_codes\nnew-user,新用户,vm_reader\n')
        definition = RoleDefinition.objects.get(group_id=role['id'])
        definition.revision += 1
        definition.save()
        batch = self.execute(response.json()['id'])
        self.assertEqual(batch.state, 'PARTIAL')
        self.assertFalse(get_user_model().objects.filter(username='new-user').exists())

    def test_xlsx_roundtrip_and_formula_protection(self):
        data = file_bytes(
            ['username', 'display_name', 'role_codes'],
            [{'username': 'xlsx-user', 'display_name': '=1+1', 'role_codes': 'Viewer'}],
            'xlsx',
        )
        rows = parse_file(SimpleUploadedFile('users.xlsx', data))
        self.assertEqual(rows[0]['input']['display_name'], "'=1+1")
        workbook = Workbook()
        workbook.active.append(['username', 'display_name'])
        workbook.active.append(['formula-user', '=1+1'])
        output = io.BytesIO()
        workbook.save(output)
        with self.assertRaises(AppError):
            parse_file(SimpleUploadedFile('users.xlsx', output.getvalue()))

    def test_export_filters_and_owner_boundary(self):
        user = get_user_model().objects.create_user('export-user', email='private@example.test')
        response = self.post(
            '/api/v1/users/batches',
            {'kind': 'export', 'fields': ['username'], 'filters': {'search': 'export-user'}},
        )
        self.assertEqual(response.status_code, 202, response.content)
        batch = AccountBatch.objects.get(pk=response.json()['id'])
        self.assertEqual(batch.options['ids'], [user.pk])
        execute_account_batch(batch.task)
        download = self.client.get(f'/api/v1/users/batches/{batch.pk}/download')
        self.assertEqual(download.status_code, 200)
        self.assertNotIn(b'private@', download.content)
        other = get_user_model().objects.create_superuser('other-admin', password='OtherAdm1nPass')
        self.client.force_login(other)
        self.assertEqual(self.client.get(f'/api/v1/users/batches/{batch.pk}').status_code, 404)

    def test_normal_user_cannot_manage_roles_or_batches(self):
        user = get_user_model().objects.create_user('ordinary', password='Ord1naryPass')
        user.groups.add(Group.objects.get(name='Viewer'))
        self.client.force_login(user)
        self.assertEqual(self.role().status_code, 403)
        self.assertEqual(
            self.post(
                '/api/v1/users/batches', {'kind': 'export', 'fields': ['username']}
            ).status_code,
            403,
        )

    def test_role_lifecycle_and_builtin_protection(self):
        response = self.role()
        self.assertEqual(response.status_code, 201, response.content)
        role = response.json()
        changed = self.client.patch(
            f'/api/v1/console/roles/{role["id"]}',
            {
                'code': role['code'],
                'display_name': '新名称',
                'permissions': ['instances.view_instance'],
                'revision': role['revision'],
            },
            content_type='application/json',
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(self.client.delete(f'/api/v1/console/roles/{role["id"]}').status_code, 204)
        builtin = Group.objects.get(name='Admin')
        self.assertEqual(self.client.delete(f'/api/v1/console/roles/{builtin.pk}').status_code, 409)
        self.assertEqual(
            self.role('bad_role', permissions=['accounts.manage_user']).status_code, 400
        )
        self.assertEqual(
            self.role('bad_dependency', permissions=['instances.start_instance']).status_code, 400
        )

    def test_last_administrator_and_session_revocation(self):
        response = self.client.patch(
            f'/api/v1/users/{self.admin.pk}', {'is_active': False}, content_type='application/json'
        )
        self.assertEqual(response.status_code, 409, response.content)
        user = get_user_model().objects.create_user('session-user', password='Sess1onPassword')
        viewer = Client()
        viewer.force_login(user)
        self.assertEqual(viewer.get('/api/v1/auth/me').status_code, 200)
        invalidate_user(user)
        self.assertEqual(viewer.get('/api/v1/auth/me').status_code, 401)

    def test_action_specific_scopes_do_not_cross_roles(self):
        a = Node.objects.create(name='scope-a', endpoint='http://127.0.0.1:9101')
        b = Node.objects.create(name='scope-b', endpoint='http://127.0.0.1:9102')
        first = self.role('reader_a', scope='nodes', node_ids=[a.pk]).json()
        second = self.role(
            'operator_b',
            scope='nodes',
            node_ids=[b.pk],
            permissions=['instances.view_instance', 'instances.start_instance'],
        ).json()
        user = get_user_model().objects.create_user('scoped')
        user.groups.add(first['id'], second['id'])
        self.assertEqual(limit_nodes(user, {a.pk, b.pk}, 'instances.start_instance'), {b.pk})
        UserProfile.objects.create(user=user, display_name='范围', node_scope=[a.pk])
        self.assertEqual(
            limit_nodes(
                get_user_model().objects.get(pk=user.pk), {a.pk, b.pk}, 'instances.start_instance'
            ),
            set(),
        )

    def test_expiry_erases_payload(self):
        batch = AccountBatch.objects.create(
            owner=self.admin,
            kind='export',
            file_data=b'private',
            rows=[{'email': 'private'}],
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        call_command('cleanup_account_batches', stdout=io.StringIO())
        batch.refresh_from_db()
        self.assertIsNone(batch.file_data)
        self.assertEqual(batch.rows, [])
        self.assertEqual(batch.state, 'EXPIRED')

    def test_assigned_role_cannot_be_deleted_and_edit_revokes_session(self):
        role = self.role().json()
        user = get_user_model().objects.create_user('role-session', password='Sess1onPassword')
        user.groups.add(role['id'])
        viewer = Client()
        viewer.force_login(user)
        self.assertEqual(self.client.delete(f'/api/v1/console/roles/{role["id"]}').status_code, 409)
        response = self.client.patch(
            f'/api/v1/console/roles/{role["id"]}',
            {
                'code': role['code'],
                'display_name': '已停用',
                'permissions': ['instances.view_instance'],
                'enabled': False,
                'revision': role['revision'],
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(
            get_user_model().objects.get(pk=user.pk).has_perm('instances.view_instance')
        )
        self.assertEqual(viewer.get('/api/v1/auth/me').status_code, 401)

    def test_sensitive_export_requires_separate_permission(self):
        from django.contrib.auth.models import Permission

        group = Group.objects.get(name='Admin')
        group.permissions.remove(
            Permission.objects.get(
                content_type__app_label='accounts', codename='export_sensitive_user'
            )
        )
        user = get_user_model().objects.create_user('limited-admin', password='Adm1nPassword')
        user.groups.add(group)
        self.client.force_login(user)
        response = self.post(
            '/api/v1/users/batches', {'kind': 'export', 'fields': ['username', 'email']}
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_personal_quota_overrides_and_last_admin_role_protection(self):
        from common.quota import enforce_quota, quota_for

        user = get_user_model().objects.create_user('zero-quota')
        UserProfile.objects.create(user=user, display_name='配额', quota_overrides={'instances': 0})
        self.assertEqual(quota_for(user)['limits']['instances'], 0)
        with self.assertRaises(AppError):
            enforce_quota(user, vcpu=1, memory_mib=512, disk_gib=10)
        self.admin.is_superuser = False
        self.admin.save()
        self.admin.groups.add(Group.objects.get(name='Admin'))
        self.client.force_login(self.admin)
        response = self.client.patch(
            f'/api/v1/users/{self.admin.pk}', {'roles': ['Viewer']}, content_type='application/json'
        )
        self.assertEqual(response.status_code, 409, response.content)
