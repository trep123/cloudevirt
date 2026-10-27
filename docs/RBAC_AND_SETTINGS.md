# CloudVirt 角色权限与系统设置

- 版本：1.0（草案）　日期：2026-10-26
- 上游：《手册》第 4、17 章；数据模型见 DATA_MODEL.md；页面见 FRONTEND_UX_SPEC.md。
- 原则：**前端隐藏不是权限边界**；所有判定在后端完成，未认证 401、无权限 403。

## 0. 实现状态（2026-10-26）

| 能力 | 状态 | 落地位置 |
| --- | --- | --- |
| 角色与权限矩阵 | 已实现 | `apps/accounts/roles.py`，`sync_roles` 命令 + post_migrate 自动同步 |
| 登录/登出/改密、锁定与限流 | 已实现 | `apps/accounts/services.py`、`views.py` |
| 权限判定与拒绝审计 | 已实现 | `common/permissions.py`（`check_permission`、`RequiresPermission`） |
| 用户管理（创建/更新/停用/重置密码） | 已实现 | `apps/accounts/views.py` |
| 任务查看/取消/重试 | 已实现 | `apps/tasks/views.py`，权限 `tasks.view_task` / `cancel_task` / `retry_task` |
| 镜像查看/导入/删除 | 已实现 | `apps/images/views.py`，权限 `images.view_image` / `add_image` / `delete_image` |
| 实例查看/创建 | 已实现 | `apps/instances/views.py`，权限 `instances.view_instance` / `add_instance` |
| 实例启动/关机/强停/重启 | 已实现 | 权限 `instances.start_instance` / `shutdown_instance` / `force_stop_instance` / `reboot_instance` |
| 实例删除与删盘 | 已实现 | `instances.delete_instance`；删盘另需 `instances.delete_disk_instance`（仅 Admin） |
| 镜像引用保护 | 已实现 | 删除被实例引用的镜像返回 409 `IMAGE_IN_USE` |
| 网络白名单 | 已实现 | `apps/networks/`，权限 `networks.view_network` / `manage_network`（仅 Admin）；管理网禁止接入 |
| 首个管理员引导 | 已实现 | `bootstrap_admin` 命令（需 `CLOUDVIRT_BOOTSTRAP_ADMIN=true`） |
| 审计事件 | 已实现 | `apps/audit`（事件模型 + `record_audit`） |
| 节点注册/刷新权限 | 已实现 | `nodes.add_node`、`nodes.refresh_node`（随节点模型同步到角色） |
| 系统设置表 | 待阶段 4 | 当前阈值走环境变量（见第 8 章） |
| 密码策略在线配置 | 待阶段 4 | 当前走 `SECURITY_*` 环境变量 |

已知限制（模块 E）：

1. MVP 采用「登记节点已有文件」的导入方式（Agent 负责检查文件），**尚未实现浏览器上传通道**；
2. 镜像引用检查已接入：删除被实例引用的镜像返回 409 `IMAGE_IN_USE`。

## 1. 角色定义

| 角色 | 定位 | 典型使用者 | Django 映射 |
| --- | --- | --- | --- |
| Admin | 系统配置、节点、镜像、实例全局管理；用户与权限管理；审计查看 | 平台管理员 | Group `Admin` |
| Operator | 在**授权范围内**创建、启动、关机、重启虚拟机；可导入镜像 | 业务运维 | Group `Operator` |
| Viewer | 只读查看节点、镜像、实例、任务 | 审计/观察人员 | Group `Viewer` |

- 角色即 Django Group，权限即 `Permission`（ADR-006）。初始化由数据迁移创建三个 Group 并绑定权限，禁止在代码里硬编码角色名判断（统一走 Permission）。
- 用户可同时属于多个 Group；权限取并集；对象级范围另按第 4 章判定。

## 2. 权限码表

| 权限 codename | 说明 | Admin | Operator | Viewer |
| --- | --- | --- | --- | --- |
| `node.view` | 查看节点与资源 | ✅ | ✅ | ✅ |
| `node.create` | 注册节点 | ✅ | ❌ | ❌ |
| `node.update` | 修改节点信息、置维护态 | ✅ | ❌ | ❌ |
| `node.delete` | 注销节点 | ✅ | ❌ | ❌ |
| `node.refresh` | 主动刷新节点资源 | ✅ | ✅ | ❌ |
| `image.view` | 查看镜像 | ✅ | ✅ | ✅ |
| `image.upload` | 导入/登记镜像 | ✅ | ✅ | ❌ |
| `image.delete` | 删除镜像 | ✅ | ✅（仅自己创建的） | ❌ |
| `network.view` | 查看网络 | ✅ | ✅ | ✅ |
| `network.manage` | 新增/变更网络白名单 | ✅ | ❌ | ❌ |
| `instance.view` | 查看实例 | ✅ | ✅ | ✅ |
| `instance.create` | 创建实例 | ✅ | ✅（授权节点内） | ❌ |
| `instance.start` | 启动 | ✅ | ✅（授权范围内） | ❌ |
| `instance.shutdown` | 正常关机 | ✅ | ✅（授权范围内） | ❌ |
| `instance.reboot` | 重启 | ✅ | ✅（授权范围内） | ❌ |
| `instance.force_stop` | 强制停止（断电风险，需二次确认 + 审计） | ✅ | ✅（授权范围内） | ❌ |
| `instance.delete` | 删除实例（注销记录） | ✅ | ✅（授权范围内） | ❌ |
| `instance.delete_disk` | 删除时一并删除虚拟磁盘（不可逆，需输入确认 + 审计） | ✅ | ❌ | ❌ |
| `task.view` | 查看任务 | ✅ | ✅ | ✅ |
| `task.cancel` | 取消未开始任务 | ✅ | ✅（自己的任务） | ❌ |
| `task.retry` | 重试失败任务 | ✅ | ✅（自己的任务） | ❌ |
| `monitoring.view` | 查看监控、告警、对账差异 | ✅ | ✅ | ✅ |
| `reconciliation.handle` | 处理对账差异（人工修复） | ✅ | ❌ | ❌ |
| `audit.view` | 查看审计日志 | ✅ | ❌ | ❌ |
| `user.manage` | 用户/角色/节点授权管理 | ✅ | ❌ | ❌ |
| `settings.manage` | 修改系统设置 | ✅ | ❌ | ❌ |

- 上表是**默认基线**；Admin 可在「角色权限」页调整 Operator/Viewer 的权限集合（内置角色不可删除，可改权限）。
- 危险权限（`instance.force_stop`、`instance.delete_disk`、`user.manage`、`settings.manage`）的操作必须写审计，且建议限流。

## 3. 认证与会话

| 项 | 约定 |
| --- | --- | --- |
| 认证方式 | 同源部署：Session + CSRF；跨域/独立部署：DRF Token（见 ADR-009） |
| 登录 | 校验用户名密码 → 校验锁定状态与密码有效期 → 成功清零失败计数并写审计；失败累加计数并写审计 |
| 失败提示 | 统一文案，不泄露用户名是否存在；不返回内部堆栈 |
| 锁定策略 | 连续失败 N 次（默认 TBD）锁定 M 分钟（默认 TBD），配置化 |
| 密码策略 | 最小长度与复杂度（默认 TBD）；管理员重置后 `must_change_password=True`，首次登录强制改密 |
| 会话失效 | 401 → 前端清除本地会话并跳登录；服务端会话/Token 可撤销 |
| 登出 | 服务端失效会话/Token + 前端清除本地状态 |
| 限流 | 登录、危险操作分别限流（默认 TBD），触发返回 429 `RATE_LIMITED` |
| 审计 | 登录成功/失败、登出、权限被拒（DENIED）均需记录 |

## 4. 对象级授权规则

判定顺序（任一不满足即 403，并写 `result=DENIED` 审计）：

```text
1) 是否认证？否 → 401
2) 是否具备该操作的 Permission（角色维度）？否 → 403
3) 对象级：
   - 节点：Admin 放行；Operator 需 operation 属于 {view} 或 NodeAccess(node, user) 允许；Viewer 仅 view
   - 实例：Admin 放行；Operator 需 (created_by == user) 或 NodeAccess(instance.node, user).can_operate；Viewer 仅 view
   - 镜像：Admin 放行；Operator 删除/覆盖需 created_by == user；所有角色 view
   - 任务：Admin 放行；Operator 仅自己的任务；Viewer 仅 view
   - 网络：view 对所有已认证用户；变更需 network.manage（仅 Admin）
4) 状态校验（不属于权限但常在同时判定）：节点离线 → 409 NODE_OFFLINE；任务进行中 → 409 OPERATION_IN_PROGRESS
```

- 节点授权数据来自 `nodes_nodeaccess`（DATA_MODEL.md 4.4），由 Admin 在用户管理页配置并写审计。
- **禁止**以客户端提交的 `user_id`、`is_admin` 等字段判定身份或权限，一律取会话/Token 主体。
- 对象级判定集中在服务层函数（如 `can_operate_instance(user, instance, action)`），视图与任务执行器共用，避免两套判定。

## 5. 首个管理员与用户生命周期

| 场景 | 规则 |
| --- | --- | --- |
| 首个管理员 | 通过一次性 bootstrap 管理命令创建（需部署环境显式开关，如 `CLOUDVIRT_BOOTSTRAP_ADMIN`），命令输出临时口令或强制首次改密；**禁止开放无认证注册接口** |
| 新建用户 | Admin 在用户管理页创建：用户名、显示名、角色、节点授权、初始口令（可随机生成 + 强制改密） |
| 改密/重置 | 自助改密校验旧密码与策略；Admin 重置后强制改密并写审计 |
| 禁用/启用 | 禁用后会话立即失效，保留用户记录与审计链；不物理删除 |
| 删除 | 优先禁用；确需删除使用 `SET_NULL` 保留审计关联（AuditEvent.actor_username 留痕） |
| 用户自助 | 个人设置：显示名、语言、改密；**不得自助改角色** |

## 6. 用户管理与角色权限页面（Admin）

| 页面 | 操作 | 审计要求 |
| --- | --- | --- |
| 用户管理 | 新建、编辑、改角色、配置节点授权、重置密码、禁用/启用、删除 | 全部记录（含变更前后关键字段） |
| 角色权限 | 查看权限矩阵、调整 Operator/Viewer 权限、查看成员 | 记录变更项 |
| 系统设置 | 修改运行时设置项、恢复默认值 | 记录 key 与新旧值 |
| 审计日志 | 按操作者/动作/对象/结果/时间筛选与导出 | 只读 |

## 7. Agent 侧权限边界

- Agent 不识别用户与角色，只校验共享 Token 与请求合法性（白名单操作、路径与参数校验）。
- 后端调用 Agent 前必须已完成用户侧权限判定；`CLOUDVIRT_ALLOW_DESTRUCTIVE` 只是宿主机侧额外开关，**不能替代后端授权**。
- Agent 仅监听本机或管理网地址，端口仅允许管理后端来源（ADR-005）。

## 8. 系统设置项清单（`settings_systemsetting`）

| 分组 | key | 类型 | 默认值 | 说明 | 可改角色 |
| --- | --- | --- | --- | --- | --- |
| 节点与心跳 | `node.heartbeat_interval_seconds` | int | TBD | 采集周期 | Admin |
| 节点与心跳 | `node.offline_after_seconds` | int | TBD | 连续失败转离线阈值 | Admin |
| 节点与心跳 | `node.resource_stale_after_seconds` | int | TBD | 资源数据过期阈值 | Admin |
| 节点与心跳 | `node.agent_request_timeout_seconds` | int | TBD | 调用 Agent 超时 | Admin |
| 资源上限 | `instance.max_vcpu` | int | TBD | 单实例 vCPU 上限 | Admin |
| 资源上限 | `instance.max_memory_mib` | int | TBD | 单实例内存上限 | Admin |
| 资源上限 | `instance.max_disk_gib` | int | TBD | 单实例磁盘上限 | Admin |
| 资源上限 | `resource.memory_reserve_percent` | int | TBD | 宿主机内存安全余量百分比 | Admin |
| 资源上限 | `resource.disk_reserve_percent` | int | TBD | 存储安全余量百分比 | Admin |
| 默认值 | `instance.default_vcpu` / `default_memory_mib` / `default_disk_gib` | int | TBD | 创建表单默认值 | Admin |
| 默认值 | `instance.default_network` | str | TBD | 默认网络名（须在白名单内） | Admin |
| 镜像 | `image.max_upload_bytes` | int | TBD | 单文件上传上限 | Admin |
| 镜像 | `image.allowed_formats` | list | ISO/QCOW2/RAW | 允许格式 | Admin |
| 镜像 | `image.import_timeout_seconds` | int | TBD | 导入超时 | Admin |
| 任务 | `task.max_attempts` | int | TBD | 最大重试次数 | Admin |
| 任务 | `task.retry_backoff_seconds` | int | TBD | 退避基数 | Admin |
| 任务 | `task.stuck_after_seconds` | int | TBD | 任务长时间未结束告警阈值 | Admin |
| 告警 | `alert.disk_free_percent_threshold` | int | TBD | 磁盘空间低阈值 | Admin |
| 告警 | `alert.enable_*` | bool | TBD | 各类告警开关 | Admin |
| 安全 | `security.password_min_length` | int | TBD | 密码最小长度 | Admin |
| 安全 | `security.login_max_failed` | int | TBD | 连续失败锁定阈值 | Admin |
| 安全 | `security.login_lock_seconds` | int | TBD | 锁定时长 | Admin |
| 展示 | `ui.page_size` / `ui.poll_interval_ms` | int | TBD | 列表分页与轮询默认值 | Admin |

- 敏感项（Agent Token、数据库串、密钥）**不进入本表**，只记录环境变量名，页面显示为「由环境变量注入（不可在线修改）」。
- 所有设置变更写入审计并可恢复默认值；修改后立即生效，需评估进行中任务的影响。

## 9. 权限测试清单

| 用例 | 预期 |
| --- | --- |
| 未认证访问实例列表 | 401 |
| Viewer 创建实例 | 403 |
| Operator 在未授权节点创建 | 403 |
| Operator 操作他人且未授权的实例 | 403 |
| Operator 在授权节点创建 | 202 |
| Operator 强停自有实例（已确认） | 202 + 审计 |
| Operator 彻底删除（含磁盘） | 403（仅 Admin） |
| Admin 任一操作 | 按矩阵通过 |
| 伪造 user_id / 伪造角色字段 | 无效，以会话主体为准 |
| 会话失效后请求 | 401，前端跳登录 |
| 登录连续失败达阈值 | 锁定并审计，提示不泄露用户名是否存在 |
| 危险操作审计 | 含操作者、对象、结果、时间、request_id |

## 10. 待定项

- 是否需要更细的“项目/租户”维度：MVP 不做，以节点授权替代；多租户需求另立阶段。
- 各阈值类设置的默认值需结合真实宿主机容量实测后回填（当前均标 TBD）。
- Admin 是否可自定义新增角色：MVP 仅允许调整 Operator/Viewer 权限集合；自定义角色待评估。
