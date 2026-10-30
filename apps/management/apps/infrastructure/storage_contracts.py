"""Versioned storage extension contracts. No SDK, credentials or network IO here."""

from dataclasses import dataclass
from typing import Protocol

from common.errors import AppError, ErrorCode

CONTRACT_VERSION = 1
DRIVERS = {
    'directory': {
        'kind': 'file',
        'usages': ['vm_disks', 'images', 'backups'],
        'configuration_fields': ['path'],
    },
    'ceph_rbd': {
        'kind': 'block',
        'usages': ['vm_disks'],
        'configuration_fields': ['monitors', 'pool', 'namespace', 'user'],
    },
    's3': {
        'kind': 'object',
        'usages': ['images', 'backups'],
        'configuration_fields': ['endpoint', 'bucket', 'region', 'prefix', 'path_style'],
    },
}


@dataclass(frozen=True)
class VolumeReference:
    backend_id: int
    volume_id: str


@dataclass(frozen=True)
class ObjectReference:
    backend_id: int
    key: str
    version_id: str | None = None


@dataclass(frozen=True)
class OperationContext:
    operation_id: str  # Stable task/idempotency key, supplied by the control plane.
    actor_id: int


class StorageDriver(Protocol):
    def probe(self) -> dict: ...
    def capacity(self) -> dict: ...


class VolumeDriver(StorageDriver, Protocol):
    def create_volume(self, context: OperationContext, size_bytes: int) -> VolumeReference: ...
    def delete_volume(self, context: OperationContext, volume: VolumeReference) -> None: ...
    def snapshot(self, context: OperationContext, volume: VolumeReference) -> str: ...
    def restore(
        self, context: OperationContext, volume: VolumeReference, snapshot_id: str
    ) -> None: ...


class ObjectDriver(StorageDriver, Protocol):
    def begin_upload(self, context: OperationContext, key: str, size_bytes: int) -> dict: ...
    def complete_upload(
        self, context: OperationContext, upload_id: str, parts: list[dict]
    ) -> ObjectReference: ...
    def abort_upload(self, context: OperationContext, upload_id: str) -> None: ...
    def download(self, context: OperationContext, obj: ObjectReference) -> dict: ...
    def delete_object(self, context: OperationContext, obj: ObjectReference) -> None: ...


def driver_catalog():
    return [
        dict(
            code=code,
            **definition,
            contract_version=CONTRACT_VERSION,
            implemented=False,
            available=False,
            capabilities=[],
            reason='仅预留接口，尚未安装并接入运行驱动',
        )
        for code, definition in DRIVERS.items()
    ]


def resolve_driver(backend):
    # Intentionally fail closed. Future adapters must be explicitly registered and wired
    # into resource ownership, quota, tasks, Agent and libvirt before activation.
    raise AppError(ErrorCode.CONFLICT, '存储驱动尚未接入，当前配置仅为草稿，不能执行存储操作')
