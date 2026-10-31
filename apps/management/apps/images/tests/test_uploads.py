"""Browser upload ownership, bounds, asynchronous verification and provenance."""

import uuid
from unittest import mock
from urllib.parse import quote

from django.test import TestCase

from apps.images.models import Image, ImageStatus
from apps.images.uploads import CHUNK_BYTES, execute_image_import
from apps.instances.tests.helpers import make_node, make_user
from apps.nodes.models import NodeAccess, NodePermission
from apps.tasks.models import Task
from common.errors import AppError, ErrorCode

INFO = {'format': 'QCOW2', 'size_bytes': 4, 'virtual_size_bytes': 1024, 'checksum_sha256': 'a' * 64}


class UploadTests(TestCase):
    def directory(self, upload_id):
        return f'images/user-{self.owner.pk}/{uuid.UUID(upload_id).hex}'

    def setUp(self):
        self.owner = make_user('upload-owner', 'Operator')
        self.other = make_user('upload-other', 'Operator')
        self.node = make_node()
        self.client.force_login(self.owner)
        self.data = {
            'id': str(uuid.uuid4()),
            'name': 'browser-upload',
            'node': self.node.pk,
            'original_name': 'rocky 10.qcow2',
            'size_bytes': 4,
        }

    def start(self):
        response = self.client.post(
            '/api/v1/images/uploads', self.data, content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        return response.json()['id']

    def test_start_is_idempotent_but_different_file_is_rejected(self):
        upload_id = self.start()
        self.assertEqual(
            self.client.post(
                '/api/v1/images/uploads', self.data, content_type='application/json'
            ).json()['id'],
            upload_id,
        )
        changed = {**self.data, 'size_bytes': 5}
        self.assertEqual(
            self.client.post(
                '/api/v1/images/uploads', changed, content_type='application/json'
            ).status_code,
            409,
        )
        self.assertEqual(Image.objects.count(), 1)
        self.assertEqual(Image.objects.get().node_id, self.node.pk)
        self.assertTrue(
            Image.objects.get().relative_path.startswith(self.directory(upload_id) + '/')
        )
        self.assertEqual(Image.objects.get().status, ImageStatus.UPLOADING)

    @mock.patch('apps.images.uploads.AgentClient')
    def test_other_user_cannot_read_write_complete_or_cancel_session(self, agent):
        upload_id = self.start()
        self.client.force_login(self.other)
        path = f'/api/v1/images/uploads/{upload_id}'
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(
            self.client.put(
                path + '/chunk?offset=0', b'data', content_type='application/octet-stream'
            ).status_code,
            404,
        )
        self.assertEqual(self.client.post(path + '/complete').status_code, 404)
        self.assertEqual(self.client.delete(path).status_code, 404)
        agent.assert_not_called()

    def test_node_acl_cannot_be_bypassed(self):
        NodeAccess.objects.create(
            node=self.node, user=self.other, permission=NodePermission.OPERATE
        )
        response = self.client.post(
            '/api/v1/images/uploads', self.data, content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Image.objects.exists())

    @mock.patch('apps.images.uploads.AgentClient')
    def test_chunk_is_bounded_and_forwarded_only_to_image_node(self, agent):
        upload_id = self.start()
        path = f'/api/v1/images/uploads/{upload_id}/chunk?offset=0'
        self.assertEqual(
            self.client.put(
                path, b'x' * (CHUNK_BYTES + 1), content_type='application/octet-stream'
            ).status_code,
            400,
        )
        agent.assert_not_called()
        agent.return_value.upload_chunk.return_value = {'offset': 4}
        self.assertEqual(
            self.client.put(path, b'data', content_type='application/octet-stream').status_code, 200
        )
        agent.assert_called_once_with(self.node.endpoint, timeout=120)
        agent.return_value.upload_chunk.assert_called_once_with(
            uuid.UUID(upload_id).hex, 0, 4, '.qcow2', b'data', directory=self.directory(upload_id)
        )

    @mock.patch('apps.images.uploads.AgentClient')
    def test_complete_requires_all_bytes_and_only_queues_one_task(self, agent):
        upload_id = self.start()
        path = f'/api/v1/images/uploads/{upload_id}/complete'
        agent.return_value.get_json.return_value = {'offset': 3, 'published': False}
        self.assertEqual(self.client.post(path).status_code, 409)
        agent.return_value.get_json.return_value = {'offset': 4, 'published': False}
        first, repeated = self.client.post(path), self.client.post(path)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.json()['task_id'], repeated.json()['task_id'])
        self.assertEqual(Task.objects.filter(type='IMAGE_IMPORT').count(), 1)
        self.assertEqual(Image.objects.get().status, ImageStatus.VERIFYING)
        agent.return_value.inspect_image.assert_not_called()

    @mock.patch('apps.images.uploads.AgentClient')
    def test_worker_publishes_then_uses_real_size_hash_and_format(self, agent):
        upload_id = self.start()
        image = Image.objects.get()
        task = Task.objects.create(
            type='IMAGE_IMPORT',
            resource_type='image',
            resource_id=str(image.pk),
            requested_by=self.owner,
        )
        agent.return_value.inspect_image.return_value = INFO
        execute_image_import(task)
        image.refresh_from_db()
        self.assertEqual(image.status, ImageStatus.READY)
        self.assertEqual(image.checksum_sha256, INFO['checksum_sha256'])
        agent.return_value.request_json.assert_called_once_with(
            f'/api/v1/images/uploads/{uuid.UUID(upload_id).hex}/complete'
            f'?directory={quote(self.directory(upload_id), safe="")}',
            'POST',
            {'size_bytes': 4, 'extension': '.qcow2'},
        )

    @mock.patch('apps.images.uploads.AgentClient')
    def test_worker_retains_agent_failure_and_never_marks_ready(self, agent):
        self.start()
        image = Image.objects.get()
        task = Task.objects.create(
            type='IMAGE_IMPORT',
            resource_type='image',
            resource_id=str(image.pk),
            requested_by=self.owner,
        )
        agent.return_value.inspect_image.side_effect = AppError(
            ErrorCode.NOT_FOUND,
            '节点镜像目录中找不到文件',
            details={'agent_request_id': 'node-request-123'},
        )
        with self.assertRaises(AppError):
            execute_image_import(task)
        image.refresh_from_db()
        self.assertEqual(image.status, ImageStatus.FAILED)
        self.assertIn('找不到文件', image.error_message)
        self.assertIn('node-request-123', image.error_message)

    @mock.patch('apps.images.uploads.AgentClient')
    def test_cancellation_only_cleans_private_partial_and_soft_deletes_record(self, agent):
        upload_id = self.start()
        response = self.client.delete(f'/api/v1/images/uploads/{upload_id}')
        self.assertEqual(response.status_code, 204)
        self.assertTrue(Image.objects.get().is_deleted)
        agent.return_value.request_json.assert_called_once_with(
            f'/api/v1/images/uploads/{uuid.UUID(upload_id).hex}?extension=.qcow2'
            f'&directory={quote(self.directory(upload_id), safe="")}',
            'DELETE',
        )

    @mock.patch('apps.nodes.client.AgentClient.delete_image')
    def test_legacy_image_requires_explicit_node_before_file_purge(self, remove):
        image = Image.objects.create(
            name='legacy', format='QCOW2', relative_path='legacy.qcow2', status=ImageStatus.FAILED
        )
        response = self.client.delete(f'/api/v1/images/{image.pk}?purge_file=true')
        self.assertEqual(response.status_code, 409)
        remove.assert_not_called()
        self.assertEqual(
            self.client.delete(f'/api/v1/images/{image.pk}?purge_file=false').status_code, 204
        )
