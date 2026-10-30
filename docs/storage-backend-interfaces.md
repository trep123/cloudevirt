# 存储接入接口 v1（仅预留）

## 当前边界

只提供管理员 API、草稿连接配置持久化、参数校验和 Python 驱动 Protocol。没有连接 Ceph、MinIO 或任何 S3 服务；没有安装 SDK、读取凭据、创建 bucket/pool、修改节点挂载或迁移现有磁盘。没有添加前端接入页面。

所有新连接固定为 `state=draft, available=false`。不允许提交 enabled/state 等字段；探测接口返回 HTTP 409/CONFLICT，不会返回虚假连接成功。现有目录池 API 保持原样，其运行能力不受新接口目录项 available=false 影响。草稿不出现在虚拟机/模板的存储选项里。

## HTTP 契约

登录管理员并携带正常 CSRF 后使用，统一前缀 `/api/v1/`，沿用项目现有 DRF 响应与错误格式。

| 方法 | 路由 | 行为 |
|---|---|---|
| GET | admin/storage-drivers/ | 驱动类型、配置字段、用途、契约版本、真实可用能力 |
| GET | admin/storage-backends/?page=1 | 草稿配置分页，20 条/页 |
| POST | admin/storage-backends/ | 创建草稿，201 |
| GET | admin/storage-backends/{id}/ | 查看草稿 |
| PUT | admin/storage-backends/{id}/ | 完整更新，必须提交当前 revision；冲突 409 |
| DELETE | admin/storage-backends/{id}/ | 仅删除草稿元数据，204；不访问实际存储 |
| POST | admin/storage-backends/{id}/probe/ | 预留连接探测，当前明确拒绝 409 |

所有接口均只允许管理员；创建、更新、删除写审计。节点普通用户不能读取 endpoint、凭据引用或配置。名称唯一，更新采用版本校验。

### MinIO / Ceph RGW / S3 示例

```json
{
  "name": "backup-s3",
  "driver": "s3",
  "usage": "backups",
  "credential_ref": "secret://backup-s3",
  "configuration": {
    "endpoint": "https://objects.example.com:9000",
    "bucket": "cloudvirt-backups",
    "region": "us-east-1",
    "prefix": "cloudvirt/",
    "path_style": true
  }
}
```

usage 只能为 images/backups，不能是 vm_disks。endpoint 只允许 HTTP(S) 源地址，不含用户密码、路径、查询串或 fragment。支持内网 IP，当前不会向地址发请求。恢复到运行磁盘需要未来适配器下载、校验并导入。

### Ceph RBD 示例

```json
{
  "name": "ceph-vms",
  "driver": "ceph_rbd",
  "usage": "vm_disks",
  "credential_ref": "secret://ceph-vms",
  "configuration": {
    "monitors": ["10.0.0.10:3300", "10.0.0.11:3300"],
    "pool": "cloudvirt",
    "namespace": "",
    "user": "cloudvirt"
  }
}
```

目录预留格式为 driver=directory、configuration={"path":"/data/cloudvirt"}，用于统一适配契约；不会调用现有节点目录池接口自动创建目录。

## 凭据与驱动扩展

- 仅接受 `secret://名称` 形式的凭据引用。不存在密钥存储/解析服务，引用尚未验证；不得提交 AccessKey、SecretKey、Ceph key、密码或 token。嵌套未知字段也拒绝，不会静默保存。
- `storage_contracts.py` 定义 OperationContext（任务幂等键与操作者）、VolumeReference（后端 ID/卷 ID）、ObjectReference（后端 ID/key/version_id）。
- VolumeDriver 预留探测、容量、创建/删除磁盘、快照及恢复；ObjectDriver 预留分片上传启动/完成/取消、下载和删除对象；不得用 S3 对象实现直接挂载运行磁盘。
- `resolve_driver` 是唯一预留解析入口，当前所有类型都失败关闭。未来实现适配器后在这里注册/选择驱动；不能只把 available 改成 true。
- 接通前还需实现凭据解析与最小权限、TLS 验证与可信节点的出口策略、超时/重试、真实能力探测；对象完整性需显式摘要校验，不能将所有 ETag 当作 MD5。
- 运行磁盘适配器需接入 Agent/libvirt、所有权、配额、异步任务、幂等、审计和删除依赖检查；模型资源引用需指向 backend_id/volume_id。已有本地文件磁盘保持兼容。
- 备份适配器需实现一致性备份/恢复、分片中断清理、对象版本/保留策略与访问授权。对有版本或保留锁的对象，删除结果必须区分删除标记与物理清理。
- 正式接入后再扩展模型加入连接状态和资源关联；运行中/关联资源的配置不得沿用草稿的无条件删除或任意改驱动规则。当前草稿不关联任何业务资源。
