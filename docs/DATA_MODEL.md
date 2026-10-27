# CloudVirt 数据结构与数据库设计

- 版本：1.0（草案）　日期：2026-10-26
- 适用：Django + DRF + PostgreSQL。所有结构以实现为准，本文是**唯一结构约定**，改结构必须先改本文。
- 关联：架构见 ARCHITECTURE.md；权限见 RBAC_AND_SETTINGS.md；任务流见 IMPLEMENTATION_TASKBOOK.md 模块 G/H/J。

## 1. 通用约定

| 项 | 约定 |
| --- | --- |
| 主键 | 默认 `BigAutoField`；Task 使用 `UUIDField(primary_key=True, default=uuid4)` |
| 时间 | 统一 `DateTimeField` 存 UTC；API 输出 ISO 8601（`Z` 结尾） |
| 枚举 | 使用 `models.TextChoices` 类，存大写字符串（如 `RUNNING`），禁止裸整数魔法值 |
| 金额/容量 | 字节用 `BigIntegerField`；内存 MiB、磁盘 GiB 用 `PositiveIntegerField`，字段名带单位后缀 |
| 软删除 | 需要保留审计链的业务表加 `is_deleted`（默认 False）+ `deleted_at`，并建立索引 |
| 外键删除 | 业务主数据用 `PROTECT`（节点、镜像、网络）；从属数据用 `CASCADE`（采样、事件、预留）；审计留痕用 `SET_NULL` |
| JSON | 仅用于非结构化快照（任务 payload、对账详情），**禁止存密钥/Token** |
| 迁移 | 每次模型变更必须生成迁移；CI 执行 `makemigrations --check --dry-run` |

## 2. 全局枚举字典

| 枚举 | 取值 | 落库字段 |
| --- | --- | --- |
| 节点状态 | `UNKNOWN` / `ONLINE` / `DEGRADED` / `OFFLINE` / `MAINTENANCE` | Node.status |
| 镜像格式 | `ISO` / `QCOW2` / `RAW` | Image.format |
| 镜像状态 | `UPLOADING` / `VERIFYING` / `READY` / `FAILED` / `DELETING` | Image.status |
| 实例期望状态 | `RUNNING` / `SHUTOFF` | Instance.desired_state |
| 实例观测状态 | `SHUTOFF` / `RUNNING` / `PAUSED` / `CRASHED` / `UNKNOWN` | Instance.observed_state |
| 任务状态（实例 operation_status 复用） | `PENDING` / `VALIDATING` / `PREPARING` / `CREATING` / `VERIFYING` / `SUCCEEDED` / `FAILED` / `CANCELLED` / `RECONCILING` | Instance.operation_status、Task.status |
| 任务类型 | `INSTANCE_CREATE` / `INSTANCE_START` / `INSTANCE_SHUTDOWN` / `INSTANCE_FORCE_STOP` / `INSTANCE_REBOOT` / `INSTANCE_DELETE` / `IMAGE_IMPORT` / `IMAGE_DELETE` / `NODE_REFRESH` / `RECONCILE` | Task.type |
| 磁盘角色 | `SYSTEM` / `DATA` | Disk.role |
| 磁盘状态 | `CREATING` / `READY` / `DELETING` / `DELETED` / `FAILED` | Disk.status |
| 网络类型 | `LIBVIRT_NETWORK` / `BRIDGE` / `OVS` | Network.type |
| 网络可用性 | `ACTIVE` / `INACTIVE` / `UNKNOWN` | NetworkAvailability.status |
| 预留状态 | `HELD` / `COMMITTED` / `RELEASED` / `EXPIRED` | ResourceReservation.status |
| 审计结果 | `SUCCESS` / `FAILURE` / `DENIED` | AuditEvent.result |
| 告警级别 | `INFO` / `WARNING` / `CRITICAL` | Alert.level |
| 告警状态 | `ACTIVE` / `ACKED` / `RESOLVED` | Alert.status |
| 对账差异处理 | `PENDING` / `AUTO_FIXED` / `MANUAL` / `IGNORED` | ReconciliationDiff.resolution |
| 角色 | `Admin` / `Operator` / `Viewer`（映射为 Django Group） | auth_group |

## 3. 实体关系总览

```text
auth_user ─1:1─ UserProfile            auth_group ─n:n─ auth_permission
    │                                        │(Group 成员)
    │ created_by                             │
    ▼                                        ▼
 Node ─1:n─ NodeResourceSample         NodeAccess(user, node, can_create, can_operate)
   │1:n                                      ▲
   ▼                                         │ 对象级授权依据
 Instance ─n:1─ Image                        │
   │  ├─1:n─ Disk ──(path 受 Agent 根目录约束)
   │  ├─n:1─ Network ─1:n─ NetworkAvailability(node)
   │  └─1:n─ Task(type,status,idempotency_key) ─1:n─ TaskEvent
   │                    │1:1
   │                    ▼
   │            ResourceReservation(node, vcpu/mem/disk, status)
   ▼
 AuditEvent(actor, action, target, result)    Alert(node/instance)   ReconciliationRun ─1:n─ ReconciliationDiff
```

## 4. 表结构详细定义

### 4.1 accounts_userprofile（用户扩展档案）

| 字段 | 类型 | 约束/默认 | 说明 |
| --- | --- | --- | --- |
| id | BigAutoField | PK | |
| user_id | FK(auth.User) | unique, CASCADE | 一对一扩展，不改动内置表 |
| display_name | CharField(64) | 必填 | 展示名 |
| locale | CharField(16) | 默认 `zh-CN` | 界面语言 |
| must_change_password | BooleanField | 默认 False | 管理员重置密码后强制改密 |
| password_changed_at | DateTimeField | 可空 | 密码有效期校验依据 |
| failed_login_count | PositiveIntegerField | 默认 0 | 连续失败计数，成功后清零 |
| locked_until | DateTimeField | 可空 | 锁定截止，登录时校验 |
| last_login_ip | GenericIPAddressField | 可空 | 审计辅助 |
| created_at / updated_at | DateTimeField | 自动 | |

- 认证主体复用 `django.contrib.auth.models.User`；角色复用 `Group` + `Permission`（ADR-006），**不自建用户/角色表**。

### 4.2 nodes_node（节点）

| 字段 | 类型 | 约束/默认 | 说明 |
| --- | --- | --- | --- |
| id | BigAutoField | PK | |
| name | CharField(64) | unique | 节点显示名，字符集校验 |
| endpoint | CharField(255) | 必填 | Agent 地址，形如 `http://10.0.0.11:9100` |
| status | CharField(16) | 默认 `UNKNOWN` | 见枚举；`MAINTENANCE` 由人工置位 |
| maintenance_note | TextField | 可空 | 维护原因，展示用 |
| agent_version | CharField(32) | 可空 | 心跳上报 |
| cpu_total | PositiveIntegerField | 可空 | 逻辑核心数（采集值） |
| memory_total_mib | PositiveIntegerField | 可空 | |
| memory_available_mib | PositiveIntegerField | 可空 | |
| storage_total_bytes | BigIntegerField | 可空 | |
| storage_free_bytes | BigIntegerField | 可空 | |
| resource_sampled_at | DateTimeField | 可空 | **采样时间，前端必须展示** |
| resource_is_stale | BooleanField | 默认 True | 数据过期标记，过期不得当作实时值 |
| last_seen_at | DateTimeField | 可空 | 最近成功心跳 |
| consecutive_failures | PositiveIntegerField | 默认 0 | 连续采集失败次数 |
| last_error_code / last_error_message | CharField(64) / TextField | 可空 | 最后错误，脱敏后存储 |
| heartbeat_interval_seconds | PositiveIntegerField | 默认 TBD | 采集周期 |
| offline_after_seconds | PositiveIntegerField | 默认 TBD | 离线阈值，可被系统设置覆盖 |
| is_deleted | BooleanField | 默认 False | 软删除（须先无实例） |
| created_at / updated_at | DateTimeField | 自动 | |

- 索引：`(status)`、`(last_seen_at)`、`(is_deleted, status)`。
- **不落库派生字段**：`is_schedulable` 由 `status in (ONLINE, DEGRADED)` 计算，禁止单独存一份以免不一致。

### 4.3 nodes_noderesourcesample（资源采样历史）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id / node_id | BigAutoField / FK(CASCADE) | |
| cpu_logical、memory_total_mib、memory_available_mib、storage_total_bytes、storage_free_bytes | 数值 | 与 Node 同义，历史值 |
| domain_count | PositiveIntegerField | 域数量 |
| sampled_at | DateTimeField | 采样时间 |
| raw | JSONField | Agent 原始响应（脱敏） |

- 索引：`(node_id, sampled_at DESC)`；保留期默认 TBD（建议 7 天），由清理任务按配置删除。

### 4.4 nodes_nodeaccess（节点级对象授权）

| 字段 | 类型 | 约束/默认 | 说明 |
| --- | --- | --- | --- |
| node_id / user_id | FK(Node, CASCADE) / FK(User, CASCADE) | **unique together** | 一个用户对一个节点一条 |
| can_create | BooleanField | 默认 True | 允许在该节点创建实例 |
| can_operate | BooleanField | 默认 True | 允许对该节点上的实例做生命周期操作 |
| created_by_id | FK(User, PROTECT) | 可空 | |
| created_at | DateTimeField | 自动 | |

- Admin 不受此表限制；Operator 按此表 + 实例归属判定；Viewer 只读。判定逻辑见 RBAC_AND_SETTINGS.md 第 4 章。

### 4.5 images_image（镜像）

| 字段 | 类型 | 约束/默认 | 说明 |
| --- | --- | --- | --- |
| id | BigAutoField | PK | |
| name | CharField(128) | unique（未删除范围内） | 展示名 |
| format | CharField(16) | 枚举 | ISO/QCOW2/RAW |
| relative_path | CharField(255) | 必填 | **服务端生成的相对路径**，配合 Agent 配置的镜像根目录，禁止用户指定绝对路径 |
| size_bytes | BigIntegerField | 必填 | 实际文件大小 |
| virtual_size_bytes | BigIntegerField | 可空 | `qemu-img info` 虚拟容量 |
| checksum_sha256 | CharField(64) | 必填 | 流式计算 |
| status | CharField(16) | 默认 `UPLOADING` | 见枚举 |
| os_family / os_version | CharField(32) | 可空 | 元数据 |
| error_code / error_message | CharField(64) / TextField | 可空 | 失败原因 |
| created_by_id | FK(User, PROTECT) | 可空 | |
| is_deleted / deleted_at | Boolean/DateTime | 默认 False | 软删除 |
| created_at / updated_at | DateTimeField | 自动 | |

- 索引：`(status)`、`(is_deleted, created_at)`。
- 对外只读属性 `path` 由「配置根目录 + relative_path」派生，**不落库绝对路径**。

### 4.6 networks_network / networks_networkavailability（网络）

| 表 | 字段 | 说明 |
| --- | --- | --- |
| Network | name(unique)、type、bridge、vlan_id(可空)、is_default、is_management、description、创建/更新时间 | `is_management=True` 的网络**禁止**被实例网卡接入 |
| NetworkAvailability | network_id、node_id、status、checked_at | unique(network, node)，表示某节点上该网络是否可用 |

### 4.7 instances_instance（虚拟机实例）

| 字段 | 类型 | 约束/默认 | 说明 |
| --- | --- | --- | --- |
| id | BigAutoField | PK | 对外展示可用短 ID |
| uuid | UUIDField | unique, default uuid4 | libvirt 域 UUID，服务端生成 |
| name | CharField(64) | 必填 | 用户可见名，字符集与长度校验 |
| libvirt_domain_name | CharField(128) | unique with node | 规则 `cv-{uuid前8位}`，避免重名冲突 |
| node_id | FK(Node, PROTECT) | 必填 | 所属节点 |
| image_id | FK(Image, PROTECT) | 必填 | 引用的镜像（引用存在时禁止删镜像） |
| network_id | FK(Network, PROTECT) | 可空 | 为空时使用节点默认网络（创建时解析并回填） |
| vcpu / memory_mib / disk_gib | PositiveIntegerField | 必填，>0 且有上限 | 规格 |
| autostart | BooleanField | 默认 False | 仅在后端已实现时前端才可勾选 |
| desired_state | CharField(16) | 默认 `RUNNING` | 用户期望：RUNNING/SHUTOFF |
| observed_state | CharField(16) | 默认 `UNKNOWN` | libvirt 实际状态 |
| observed_state_updated_at | DateTimeField | 可空 | 观测时间 |
| observed_state_is_stale | BooleanField | 默认 True | 节点离线/采集失败置 True |
| operation_status | CharField(16) | 默认 `PENDING` | 当前任务阶段；无进行中任务时取最近终态 |
| current_task_id | FK(Task, SET_NULL) | 可空 | 便于 409 判定与前端跳转 |
| last_error_code / last_error_message | CharField(64) / TextField | 可空 | |
| created_by_id | FK(User, PROTECT) | 必填 | 归属，用于对象级授权 |
| disks_deleted | BooleanField | 默认 False | 删除时磁盘是否已清理 |
| is_deleted / deleted_at | Boolean/DateTime | 默认 False | 软删除 |
| created_at / updated_at | DateTimeField | 自动 | |

- 唯一约束：`(node_id, libvirt_domain_name)` 唯一；`(node_id, name)` 在 `is_deleted=False` 范围内唯一（条件唯一索引）。
- 索引：`(node_id, observed_state)`、`(created_by_id, is_deleted)`、`(operation_status)`。
- **三态不得合并**：desired_state / observed_state / operation_status 必须分列。

### 4.8 instances_disk（虚拟磁盘）

| 字段 | 类型 | 约束/默认 | 说明 |
| --- | --- | --- | --- |
| id / instance_id | BigAutoField / FK(CASCADE) | | 一个实例 1 系统盘 + N 数据盘 |
| role | CharField(16) | 默认 `SYSTEM` | SYSTEM/DATA |
| name | CharField(128) | 服务端生成 `{instance_uuid}-{role}.qcow2` | 禁止用户输入 |
| relative_path | CharField(255) | unique | 相对 Agent 磁盘根目录 |
| format | CharField(16) | 默认 `QCOW2` | 稀疏优先，RAW 由配置决定 |
| size_gib | PositiveIntegerField | 必填 | 请求容量 |
| virtual_size_bytes / actual_size_bytes | BigIntegerField | 可空 | `qemu-img info` 复核值 |
| bus / target_dev | CharField(16) | 默认 `virtio` / `vda` | Domain XML 使用 |
| status | CharField(16) | 默认 `CREATING` | 见枚举 |
| is_orphan | BooleanField | 默认 False | 孤儿扫描标记 |
| created_at / updated_at | DateTimeField | 自动 | |

- 索引：`(instance_id, role)`、`(is_orphan, status)`。

### 4.9 tasks_task（异步任务）

| 字段 | 类型 | 约束/默认 | 说明 |
| --- | --- | --- | --- |
| id | UUIDField | PK, default uuid4 | 任务 ID，对外暴露 |
| type / status | CharField(32) / CharField(16) | 见枚举 | 状态默认 `PENDING` |
| resource_type / resource_id | CharField(32) / CharField(64) | 必填 | 跨类型统一标识（实例/镜像/节点） |
| requested_by_id | FK(User, PROTECT) | 可空 | 操作者 |
| idempotency_key | CharField(64) | 可空 | 幂等键，**活跃态唯一** |
| payload | JSONField | 默认 {} | 请求参数快照，**禁止含密钥/口令** |
| result | JSONField | 可空 | Agent 返回的脱敏结果 |
| attempt_count / max_attempts | PositiveIntegerField | 0 / 3(默认 TBD) | 重试控制 |
| next_retry_at | DateTimeField | 可空 | 退避时间点 |
| locked_at / locked_by | DateTimeField / CharField(64) | 可空 | worker 原子领取标记 |
| started_at / finished_at | DateTimeField | 可空 | |
| last_error_code / last_error_message | CharField(64) / TextField | 可空 | |
| parent_task_id | FK(self, SET_NULL) | 可空 | 补偿/重试子任务 |
| created_at / updated_at | DateTimeField | 自动 | |

- 索引：`(status, next_retry_at)`、`(resource_type, resource_id, status)`、`(created_at)`。
- 条件唯一：`UniqueConstraint(fields=['idempotency_key'], condition=Q(status__in=[活跃状态...]), name='uniq_active_idempotency_key')`。
- **领取必须原子**：`UPDATE ... WHERE status='PENDING' AND (locked_at IS NULL OR locked_at < 过期)` 或 `select_for_update(skip_locked=True)`，禁止先查后写。

### 4.10 tasks_taskevent（任务事件流水）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id / task_id | BigAutoField / FK(CASCADE) | |
| attempt | PositiveIntegerField | 第几次尝试 |
| from_status / to_status | CharField(16) | 状态迁移 |
| level | CharField(16) | INFO/WARNING/ERROR |
| error_code | CharField(64) | 可空 |
| message | TextField | 脱敏后的可读信息 |
| created_at | DateTimeField | |

- 索引：`(task_id, created_at)`；保留期默认 TBD（建议 30 天）。

### 4.11 resources_reservation（资源预留）

| 字段 | 类型 | 约束/默认 | 说明 |
| --- | --- | --- | --- |
| id / node_id / task_id | BigAutoField / FK(CASCADE) / FK(CASCADE) | task_id 唯一 | 一任务一预留 |
| instance_id | FK(Instance, SET_NULL) | 可空 | 创建成功后回填 |
| vcpu_reserved / memory_reserved_mib | PositiveIntegerField | 必填 | |
| disk_reserved_bytes | BigIntegerField | 必填 | |
| status | CharField(16) | 默认 `HELD` | HELD/COMMITTED/RELEASED/EXPIRED |
| expires_at | DateTimeField | 必填 | 防悬挂预留，过期由对账处理 |
| created_at / updated_at | DateTimeField | 自动 | |

- 索引：`(node_id, status)`、`(expires_at, status)`。
- 并发规则：创建时**先锁 Node 行**校验 `可用 = 总量 - 已分配 - HELD预留`，再写预留，最后提交事务；禁止“查询后判断”式的非原子校验。

### 4.12 audit_auditevent（审计事件）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id / actor_id | BigAutoField / FK(User, SET_NULL) | 操作者（用户删除后仍保留） |
| actor_username | CharField(150) | 冗余保存，便于留痕 |
| action | CharField(64) | 见 RBAC_AND_SETTINGS.md 权限码表 |
| target_type / target_id | CharField(32) / CharField(64) | 操作对象 |
| result | CharField(16) | SUCCESS/FAILURE/DENIED |
| request_id / task_id | CharField(64) / UUIDField | 可空，链路追踪 |
| node_id | FK(Node, SET_NULL) | 可空 |
| ip | GenericIPAddressField | 可空 |
| details | JSONField | 变更前后关键字段（**脱敏**） |
| created_at | DateTimeField | |

- 索引：`(target_type, target_id, created_at)`、`(actor_id, created_at)`、`(action, created_at)`；保留期默认 TBD（建议 180 天）。

### 4.13 monitoring_alert（告警）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| type | CharField(32) | NODE_OFFLINE / AGENT_AUTH_FAILURE / RESOURCE_LOW / TASK_STUCK / DISK_SPACE_LOW / LIBVIRT_UNAVAILABLE / ORPHAN_DOMAIN / ORPHAN_DISK |
| level | CharField(16) | INFO/WARNING/CRITICAL |
| node_id / instance_id | FK(SET_NULL) | 可空 |
| resource_type / resource_id | CharField | 可空 |
| message | TextField | 面向运维的可读描述 |
| status | CharField(16) | ACTIVE/ACKED/RESOLVED |
| count | PositiveIntegerField | 同类告警聚合次数 |
| first_seen_at / last_seen_at / resolved_at | DateTimeField | |

- 索引：`(status, level, last_seen_at)`；保留期默认 TBD（建议 90 天）。

### 4.14 monitoring_reconciliationrun / monitoring_reconciliationdiff（对账）

| 表 | 字段 | 说明 |
| --- | --- | --- |
| Run | started_at、finished_at、status、scope、summary(JSON) | 每次对账一轮 |
| Diff | run_id、kind、node_id、resource_type/resource_id、detail(JSON)、resolution、resolved_by_id、resolved_at、note | kind：`DB_INSTANCE_MISSING_DOMAIN` / `DOMAIN_NOT_IN_DB` / `DISK_FILE_ORPHAN` / `DISK_RECORD_MISSING_FILE` / `RESERVATION_MISMATCH` |

- 默认**只记录不自动修复**；仅对明确安全的差异执行修复，有破坏风险的转人工（ADR-008）。

### 4.15 settings_systemsetting（运行时系统设置）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| key | CharField(64) | unique，如 `node.offline_after_seconds` |
| value | JSONField | 值 |
| value_type | CharField(16) | int/bool/str/list，用于校验 |
| default_value | JSONField | 默认值快照，支持恢复默认 |
| description | TextField | 面向管理员的说明 |
| is_secret | BooleanField | 默认 False；为 True 时**不落库值**，仅存环境变量名 |
| updated_by_id / updated_at | FK(User, PROTECT) / DateTime | 变更留痕 |

- 敏感项（Token、密钥、数据库连接串）一律走环境变量，禁止写入本表。设置项清单见 RBAC_AND_SETTINGS.md 第 8 章。

## 5. 索引与约束汇总

| 表 | 约束 / 索引 | 目的 |
| --- | --- | --- |
| Node | unique(name)；idx(status)、idx(last_seen_at)、idx(is_deleted,status) | 列表筛选、离线扫描 |
| NodeAccess | unique(node_id,user_id)；idx(user_id) | 对象级授权判定 |
| Image | unique(name)；idx(status)、idx(is_deleted,created_at) | 列表与引用检查 |
| Instance | unique(uuid)；unique(node_id,libvirt_domain_name)；条件 unique(node_id,name) where not is_deleted；idx(node_id,observed_state)、idx(created_by_id,is_deleted)、idx(operation_status) | 防重名、列表、对账 |
| Disk | unique(relative_path)；idx(instance_id,role)、idx(is_orphan,status) | 孤儿扫描 |
| Task | PK(uuid)；条件 unique(idempotency_key) where 活跃；idx(status,next_retry_at)、idx(resource_type,resource_id,status) | worker 领取、同资源冲突判定 |
| Reservation | unique(task_id)；idx(node_id,status)、idx(expires_at,status) | 超分防护、过期回收 |
| AuditEvent | idx(target_type,target_id,created_at)、idx(actor_id,created_at)、idx(action,created_at) | 审计查询 |
| Alert | idx(status,level,last_seen_at) | 仪表盘告警 |

## 6. 并发与一致性规则

1. **资源预留**：`transaction.atomic()` 内 `Node.objects.select_for_update().get(pk=node_id)` → 计算可用 → 创建 Reservation → 创建 Task/Instance → 提交。禁止在事务内发起对 Agent 的 HTTP 调用。
2. **任务领取**：`select_for_update(skip_locked=True)` 或带条件的原子 UPDATE；多 worker 不得重复领取同一任务。
3. **状态回写**：条件更新 `Model.objects.filter(pk=.., operation_status='CREATING').update(...)`，返回行数为 0 说明已被其他流程改写，转入 `RECONCILING`。
4. **观测状态**：仅由采集/对账流程写入；API 请求不得直接改 observed_state。
5. **数据过期**：节点离线或采集失败时置 `resource_is_stale=True`、`observed_state_is_stale=True`，**不得用 0 覆盖已有数值**。

## 7. 迁移与变更流程

| 场景 | 要求 |
| --- | --- |
| 新增字段 | 必须可空或有默认值，避免锁表；大表加列需评估 |
| 枚举扩展 | 先加取值再放代码依赖，保证向后兼容 |
| 不可逆迁移 | 必须在文档写明恢复计划与前置备份 |
| 数据回填 | 使用独立数据迁移，禁止在业务代码里隐式修补 |
| 索引变更 | PostgreSQL 使用 `CREATE INDEX CONCURRENTLY` 思路，迁移中设置 `atomic = False`（视实现而定） |

## 8. 数据保留与清理

| 数据 | 保留策略 |
| --- | --- |
| 资源采样历史 | 保留 TBD 天（建议 7），按 `sampled_at` 清理 |
| 任务与任务事件 | 任务保留 TBD 天（建议 90），事件随任务清理 |
| 审计事件 | 保留 TBD 天（建议 180），导出归档后再清理 |
| 告警 | 保留 TBD 天（建议 90），RESOLVED 后进入清理窗口 |
| 对账差异 | 保留至处理完成 + TBD 天 |
| 实例/磁盘记录 | 软删除保留，清理需人工确认与审计 |

## 9. 待定项

- 是否引入 `django-simple-history` 之类的字段级历史表（当前用 AuditEvent 覆盖，待评估）。
- 采样/任务/审计保留期的具体天数，需运维确认后回填。
- 数据盘（DATA 角色磁盘）挂载流程是否进入 MVP：数据结构已预留，实现排阶段 3 之后。
