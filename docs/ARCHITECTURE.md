# CloudVirt 架构与接口设计

- 版本：1.0（草案）　日期：2026-10-26
- 上游：《手册》第 1、5~12、14、15 章；任务拆解见 IMPLEMENTATION_TASKBOOK.md
- 定位：实现前的**唯一结构约定**。新增文件前先查本文；与本文冲突时，先改本文再改代码。

## 1. 组件职责与边界

| 组件 | 职责 | 明确不做 |
| --- | --- | --- |
| 前端 apps/web | 展示与交互、表单即时提示、危险操作二次确认、任务轮询、错误展示 | 最终授权、资源预留、直连 Agent |
| 管理后端 apps/management | 认证授权、参数校验、资源校验与调度、任务状态机、节点 API 调用、期望/观测状态与对账、审计 | 在请求线程内等待耗时 QEMU/libvirt 操作 |
| 节点 Agent services/virt-node-agent | 宿主机上执行白名单虚拟化操作、路径与参数校验、资源采集、结构化错误 | 用户/租户/权限、前端业务逻辑 |
| libvirt / QEMU / KVM | 域/网络/存储卷生命周期管理 | 业务规则 |
| PostgreSQL | 业务状态唯一来源（用户、节点、镜像、实例、磁盘、任务、预留、审计） | 代替宿主机事实 |

- **事实来源划分**：数据库记录 = 平台业务状态；libvirt 观测 = 宿主机运行事实。二者允许短暂不一致，由任务状态机与周期对账收敛。

## 2. 目录结构（新建约定）

```text
cloude-virt/
├── README.md                       # 项目简介、依赖、启停与测试命令
├── Makefile                        # 统一入口：dev-up / test / lint / build
├── apps/
│   ├── management/                 # Django + DRF 管理后端
│   │   ├── manage.py
│   │   ├── config/                 # settings / urls / asgi / wsgi
│   │   ├── common/                 # 统一响应、错误码、分页、request_id、日志、权限基类
│   │   ├── apps/
│   │   │   ├── accounts/           # 用户、角色、权限（模块 B）
│   │   │   ├── nodes/              # 节点、心跳、资源采样（模块 C）
│   │   │   ├── images/             # 镜像登记与校验（模块 E）
│   │   │   ├── instances/          # 实例、磁盘、状态机（模块 F/G/H/I）
│   │   │   ├── tasks/              # 任务表、worker、重试、幂等、恢复（模块 J）
│   │   │   ├── networks/           # 网络白名单（模块 M）
│   │   │   ├── monitoring/         # 采集、对账、告警（模块 N）
│   │   │   └── audit/              # 审计事件（模块 B/O）
│   │   └── requirements/           # base / dev / prod + 锁文件
│   └── web/                        # React + TypeScript + Vite
│       ├── src/api/                # 唯一 API 层：客户端、类型、错误解析
│       ├── src/pages/              # 页面（见《手册》13.1 清单）
│       ├── src/components/         # 通用组件（确认对话框、状态标签、任务进度）
│       └── src/types/
├── services/
│   └── virt-node-agent/            # Go 节点 Agent（模块 D）
│       ├── cmd/virt-node-agent/
│       └── internal/{config,httpapi,auth,host,libvirt,storage,domainxml,audit}
├── deploy/{ansible,compose,systemd}
├── scripts/                        # precheck、孤儿扫描、备份等运维脚本
└── docs/                           # 本文档体系
```

- 包/目录名使用单数（`node` 而非 `nodes` 仅适用于 Go 内部包；Django app 命名沿用上表，一经确定不再更改）。
- 若实施中发现更合理的布局，必须先更新本章再落代码，禁止出现两套并存结构。

## 3. 数据模型（MVP 概览）

- 本节为**概览与索引**；字段级定义（类型、默认值、约束、索引、保留策略、并发规则）以 [DATA_MODEL.md](./DATA_MODEL.md) 为准。

| 模型 | 所属模块 | 关键字段 | 索引/约束 |
| --- | --- | --- | --- |
| User / Group / Permission | B | 复用 Django 内置；角色映射为 Group（Admin/Operator/Viewer） | 内置 |
| Node | C | name, endpoint, status, last_seen_at, last_error, consecutive_failures, cpu_total, memory_total_mib, memory_available_mib, storage_total_bytes, storage_free_bytes, agent_version, resource_sampled_at | name 唯一；status 索引 |
| Image | E | name, format, path, size_bytes, checksum_sha256, status, os_family, os_version, created_by, 时间戳 | name 唯一；status 索引 |
| Instance | G | id, uuid(唯一), name, node_id, image_id, vcpu, memory_mib, disk_gib, autostart, desired_state, observed_state, operation_status, last_error_code, last_error_message, created_by, 时间戳 | uuid 唯一；(node_id, name) 唯一；node_id/status 索引 |
| Disk | F | id, instance_id, path, format, size_bytes, status, 时间戳 | instance_id 索引；path 唯一 |
| Network | M | name, type, bridge, vlan, status, node 范围 | name 唯一 |
| Task | J | id(UUID), type, status, resource_type, resource_id, requested_by, idempotency_key, attempt_count, max_attempts, started_at, finished_at, last_error_code, last_error_message | (resource_type, resource_id, status) 索引；idempotency_key 唯一（部分索引：仅未终态） |
| ResourceReservation | H | task_id, node_id, vcpu_reserved, memory_reserved_mib, disk_reserved_bytes, status | node_id + status 索引 |
| AuditEvent | B/O | actor, action, target_type, target_id, result, request_id, 时间, 详情 | (target_type, target_id)、actor、时间 索引 |
| Alert（可选） | N | type, level, node_id, message, status, 时间 | status + 时间 索引 |

- 时间统一 UTC 存储、ISO 8601 输出。
- 软删除字段统一使用 `is_deleted`（若引入），并建立索引。

## 4. 状态机

### 4.1 观测状态 observed_state

| 值 | 来源 |
| --- | --- |
| SHUTOFF / RUNNING / PAUSED / CRASHED | libvirt 域状态映射 |
| UNKNOWN | libvirt 返回未知状态、节点离线、采集失败 |

- 映射逻辑集中在 `apps/instances/state_machine.py`，**禁止在各视图内各自 switch**。
- libvirt 未知状态一律映射 UNKNOWN，不得默认当作关机。

### 4.2 任务状态 operation_status

PENDING → VALIDATING → PREPARING → CREATING → VERIFYING → SUCCEEDED
　　↓（任一阶段失败）　　　　　　　　　　　　　　　　↓
　FAILED　　　　　　　　　　　　　　　　　RECONCILING（回写/查询不一致时）
　　↓（用户取消或策略取消）
　CANCELLED

- 状态变更使用事务 + 条件更新（乐观/行锁），禁止读-改-写覆盖。
- 同实例存在未终态任务时，新操作返回 409 `OPERATION_IN_PROGRESS`，或按明确幂等策略合并。

### 4.3 节点状态 status

UNKNOWN → ONLINE ⇄ DEGRADED → OFFLINE；MAINTENANCE 为人工置位，不被自动改写。
- OFFLINE 判定：连续采集失败且超过 `NODE_OFFLINE_AFTER_SECONDS`（可配置）。
- OFFLINE / MAINTENANCE 节点不接收新实例创建任务。

## 5. API 契约索引

### 5.1 管理后端（前缀 /api/v1/）

| 方法 | 路径 | 说明 | 成功码 |
| --- | --- | --- | --- |
| GET | /api/v1/health | 健康检查（免认证） | 200 |
| POST | /api/v1/auth/login/ | 登录 | 200 |
| POST | /api/v1/auth/logout/ | 登出 | 200 |
| GET/POST | /api/v1/nodes/ | 节点列表（`nodes.view_node`） / 注册（`nodes.add_node`） | 200 / 201 |
| GET | /api/v1/nodes/{id}/ | 节点详情（含资源与采样时间） | 200 |
| POST | /api/v1/nodes/{id}/refresh/ | 主动刷新资源（`nodes.refresh_node`，同步返回最新节点） | 200 |
| GET | /api/v1/images/ | 镜像列表 | 200 |
| POST | /api/v1/images/ | 镜像导入（上传或登记） | 202 |
| DELETE | /api/v1/images/{id}/ | 删除镜像（被引用 → 409 IMAGE_IN_USE） | 202 |
| GET/POST | /api/v1/instances/ | 实例列表 / 创建 | 200 / **202** |
| GET | /api/v1/instances/{id}/ | 实例详情 | 200 |
| POST | /api/v1/instances/{id}/start/ | 启动 | 202 |
| POST | /api/v1/instances/{id}/shutdown/ | 正常关机 | 202 |
| POST | /api/v1/instances/{id}/force-stop/ | 强制停止（高权限 + 二次确认） | 202 |
| POST | /api/v1/instances/{id}/reboot/ | 重启 | 202 |
| DELETE | /api/v1/instances/{id}/ | 删除（参数显式声明是否删除磁盘） | 202 |
| GET | /api/v1/tasks/ | 任务列表（`tasks.view_task`） | 200 |
| GET | /api/v1/tasks/{id}/ | 任务详情与事件流水 | 200 |
| POST | /api/v1/tasks/{id}/cancel/ | 取消等待中任务（`tasks.cancel_task`） | 200 |
| POST | /api/v1/tasks/{id}/retry/ | 重试失败任务（`tasks.retry_task`） | 200 |
| GET | /api/v1/tasks/{id}/ | 任务详情与进度 | 200 |
| GET | /api/v1/networks/ | 网络列表（白名单） | 200 |
| GET | /api/v1/audit/ | 审计事件 | 200 |
| GET | /api/v1/monitoring/overview/ | 资源与告警概览 | 200 |
| GET | /api/v1/monitoring/reconciliation/ | 对账差异 | 200 |

### 5.2 节点 Agent（仅管理网可见）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /health | 进程存活，`{status,version}` |
| GET | /api/v1/node/resources | CPU/内存/存储采集 + sampled_at |
| GET | /api/v1/domains | 域列表与状态 |
| POST | /api/v1/domains | 创建域（UUID 幂等） |
| GET | /api/v1/domains/{uuid} | 查询域信息 |
| POST | /api/v1/domains/{uuid}/start | 启动 |
| POST | /api/v1/domains/{uuid}/shutdown | ACPI 关机 |
| POST | /api/v1/domains/{uuid}/force-stop | 强制停止 |
| POST | /api/v1/domains/{uuid}/reboot | 重启 |
| DELETE | /api/v1/domains/{uuid} | 销毁域（参数决定是否删除磁盘） |
| POST | /api/v1/disks | 创建磁盘（路径受根目录约束） |
| GET | /api/v1/disks/{name}/info | qemu-img info 复核 |
| DELETE | /api/v1/disks/{name} | 删除磁盘（二次校验引用与路径） |
| GET | /api/v1/networks | 白名单网络列表与状态 |

- 所有 Agent 请求需 `Authorization: Bearer <token>`；失败返回统一错误结构。
- 用户侧权限与对象级授权规则见 [RBAC_AND_SETTINGS.md](./RBAC_AND_SETTINGS.md)。

### 5.3 统一错误响应

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数不符合要求",
    "details": { "memory_mib": ["必须大于 0"] },
    "request_id": "req-example"
  }
}
```

Agent 侧等价结构：{"code":"LIBVIRT_UNAVAILABLE","message":"...","request_id":"..."}（同一 API 内不得混用两种结构）。

### 5.4 统一约定（模块 L 已落地）

| 项 | 约定 |
| --- | --- |
| 编码 | JSON UTF-8，不做 \uXXXX 转义；时间 ISO 8601 UTC（`%Y-%m-%dT%H:%M:%SZ`） |
| 分页 | 参数 `page`、`page_size`；默认 20 条，上限 `API_MAX_PAGE_SIZE`（默认 100，环境变量可覆盖） |
| 链路追踪 | 请求/响应头 `X-Request-ID`；服务端生成（32 位十六进制），调用方传入且格式合法时复用；错误体必含 `request_id` |
| 幂等 | 写操作可携带 `Idempotency-Key` 请求头，服务端语义在模块 J 实现（活跃任务内唯一） |
| 错误页 | API 前缀下 404/500 均返回 JSON 错误结构，不返回 HTML 错误页 |
| 实现位置 | `common/errors.py`（错误码与 `AppError`）、`common/exceptions.py`（统一处理器）、`common/pagination.py`、`common/middleware.py`、`common/logging.py` |

### 5.5 错误码与状态码

| 错误码 | HTTP | 含义 |
| --- | --- | --- |
| UNAUTHORIZED | 401 | 未认证或 Token 无效 |
| PERMISSION_DENIED | 403 | 已认证但无权限 |
| VALIDATION_ERROR / INVALID_ARGUMENT | 400 | 参数或字段无效 |
| NOT_FOUND | 404 | 资源不存在 |
| OPERATION_IN_PROGRESS | 409 | 同资源存在未终态任务 |
| INSUFFICIENT_RESOURCE | 409 | CPU/内存/存储不足（需说明类型） |
| IMAGE_IN_USE | 409 | 镜像被实例引用，禁止删除 |
| NODE_OFFLINE | 409/503 | 节点离线不可调度 |
| LIBVIRT_UNAVAILABLE | 503 | libvirt 不可用 |
| COMMAND_TIMEOUT | 504 | 上游/命令超时 |
| OPERATION_FAILED / INTERNAL_ERROR | 500 | 未分类/内部错误 |
| RATE_LIMITED | 429 | 触发限流 |

## 6. 关键流程

### 6.1 创建实例（异步）

1. 前端提交 → 后端认证/授权 → 逐项校验（名称、节点、镜像、规格、资源）。
2. 同一事务：创建 Instance（observed=UNKNOWN, operation=PENDING）+ Task + ResourceReservation（对节点资源加锁）。
3. 事务提交后返回 202（instance + task.status_url）。
4. worker 领取任务（原子条件更新）→ 调用 Agent `POST /api/v1/domains`。
5. Agent：Token/字段校验 → 路径复核 → UUID 幂等查询 → libvirt 可用校验 → 创建磁盘 → 生成并解析校验 XML → 定义/创建域 → 回查核对 → 返回结果。
6. 后端回写：成功 → operation=SUCCEEDED、observed 由查询确认、预留转已分配；失败 → 按《手册》10.6 补偿并释放/保留预留。

### 6.2 心跳与离线判定

周期任务 → 调 `/health` 与 `/api/v1/node/resources` → 成功则更新 last_seen_at 与采样值 → 失败则累加 consecutive_failures 与 last_error（**保留上次有效资源，标记过期**）→ 超过阈值置 OFFLINE 并写审计 → 恢复后先重新采集再做实例状态对账，然后恢复调度资格。

### 6.3 删除实例

权限校验 → 明确磁盘处理选项 → 按策略关机 → 校验域 UUID → 销毁域 → （可选）删除磁盘 → 核验资源释放 → 更新数据库 → 写审计。任一步失败进入可重试删除任务状态，**不得丢失资源引用信息**。

## 7. 日志与审计字段

- 结构化日志字段：`timestamp`、`level`、`component`、`request_id`/`task_id`、`node_id`、`instance_id`、`operation`、`duration_ms`、`result`、`error_code`。
- 禁止记录：Authorization 头、用户密码、私钥、cloud-init 口令、未脱敏敏感数据、完整数据库连接串。
- 审计事件必含：操作者、操作对象、操作结果、时间；危险操作（删除、强停、镜像替换）必记录。

## 8. 关键决策记录（ADR）

| ID | 决策 | 理由 | 状态 |
| --- | --- | --- | --- |
| ADR-001 | 全部模块按 NEW 从零实现，不兼容历史代码 | 仓库仅有 1 次空提交，无历史包袱 | 已定 |
| ADR-002 | 任务系统采用“数据库任务表 + 独立 worker 轮询”，不引入 Celery/RQ | 避免多套任务系统并存（《手册》12.2） | 已定 |
| ADR-003 | API 前缀统一 `/api/v1/` | 新建项目无兼容负担，与《手册》2.1 一致 | 已定 |
| ADR-004 | MVP 虚拟磁盘默认 QCOW2，raw 由配置决定 | 稀疏分配，适合 MVP 容量规划 | 已定 |
| ADR-005 | Agent 默认绑定本机/管理网，禁止 0.0.0.0 暴露 | 《手册》2.2、17.1 | 已定 |
| ADR-006 | 角色复用 Django Group + Permission，不自建权限表 | 《手册》4.2，统一维护 | 已定 |
| ADR-007 | Django/DRF 与 Go 具体版本待安装时按兼容矩阵确定 | 环境实测未安装，禁止凭空写版本（TBD） | 待定 |
| ADR-008 | 孤儿资源默认只出报告，不自动删除 | 《手册》8.3，避免误删 | 已定 |
| ADR-009 | 认证方式：同源部署用 Session + CSRF；跨域/独立部署用 DRF Token，Token 不持久化到 localStorage | 兼顾安全与部署形态；细节见 RBAC_AND_SETTINGS.md 第 3 章 | 已定 |
| ADR-010 | 域类型默认 kvm；仅当环境显式声明 TCG（CLOUDVIRT_ALLOW_TCG=true）时使用 qemu，且相关验收必须标注「TCG 模拟，非硬件加速」 | 本环境无 /dev/kvm，需保留开发验证通路，同时禁止把 TCG 结果当作生产结论 | 已定 |
