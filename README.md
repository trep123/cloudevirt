# CloudVirt 云虚拟化管理平台

基于 QEMU/KVM + libvirt 的云虚拟化管理平台：Go 节点 Agent 负责宿主机受限操作，Django + DRF 管理后端负责任务编排与状态管理，React + TypeScript 前端提供操作界面。

- 当前阶段：单节点业务模块与控制台 UI 已实现；真实 KVM 全链路与生产验收仍以验收记录为准
- 文档入口：[docs/README.md](./docs/README.md)
- 桌面与独立视频：[实现、部署与验证记录](./docs/console-media-workspace.md)
- 状态说明：功能是否验证通过以 docs 中的验收记录为准，未验证项一律标记 NOT VERIFIED

## 1. 组件

| 目录 | 组件 | 技术栈 | 职责 |
| --- | --- | --- | --- |
| `apps/management` | 管理后端 | Python 3.14 / Django 6.1 / DRF 3.18 | 认证授权、参数校验、调度与资源预留、任务编排、审计 |
| `services/virt-node-agent` | 节点 Agent | Go 1.26 | 宿主机上的受限虚拟化操作、资源采集、结构化错误 |
| `frontend` | 前端 | React 19 + TypeScript + Vite | 登录、节点/镜像/网络/虚拟机/任务/监控页面，危险操作二次确认 |
| `deploy` | 部署 | systemd / compose | 服务单元、开发数据库、宿主机初始化 |
| `scripts` | 运维脚本 | Bash | 部署前环境检查 |

## 2. 环境要求

| 组件 | 已验证版本 | 说明 |
| --- | --- | --- |
| 操作系统 | Ubuntu 26.04.1 LTS | 目标环境为 Ubuntu Server LTS |
| Python | 3.14.4 | 后端运行时 |
| Go | 1.26.8 | Agent 构建 |
| Node / npm | v24.22.1 / 12.2.1 | 前端构建 |
| PostgreSQL | 18.6 | 业务数据库 |
| qemu-utils | 10.2.1 | 镜像与磁盘操作（qemu-img） |

宿主机侧还需 `qemu-kvm`、`libvirt-daemon-system`、`libvirt-clients` 与可用的 `/dev/kvm`（本机已开启嵌套虚拟化并通过验证，见 docs/ENVIRONMENT_DEPLOYMENT.md 第 1.3 节）。
缺少 `/dev/kvm` 的环境可执行 `CLOUDVIRT_ALLOW_TCG=true bash scripts/precheck.sh` 以 QEMU TCG 模拟降级运行（退出码 2，仅用于开发测试，性能不代表生产）。

## 3. 快速开始

Ubuntu 26 新系统的一键部署（在完整项目根目录执行）：

    sudo bash install.sh --enable-ovs --allow-destructive

参数、证书、初始口令和部署限制见 [Ubuntu 26 部署说明](docs/INSTALL_UBUNTU_26.md)。

```bash
# 1) 后端：虚拟环境 + 依赖
make venv && make backend-install

# 2) 数据库（三选一）
#   a. 本机 PostgreSQL：见 docs/ENVIRONMENT_DEPLOYMENT.md 第 5 章创建专用账户与库
#   b. 开发容器：cd deploy/compose && docker compose up -d postgres
#   c. 已有实例：设置 DATABASE_URL 环境变量

# 3) 迁移与启动
export DJANGO_DEBUG=true
export DATABASE_URL=postgresql://cloudvirt:<口令>@127.0.0.1:5432/cloudvirt
make backend-migrate
make backend-run      # http://127.0.0.1:8000/api/v1/health

# 4) 节点 Agent（需 libvirt 环境）
export CLOUDVIRT_AGENT_TOKEN=<至少 32 字节随机串>
make agent-run        # http://127.0.0.1:9100/health

# 5) 前端（开发模式会代理 /api 到 127.0.0.1:8000）
make web-install
make web-dev          # http://127.0.0.1:5173

# 6) 部署前检查
make precheck
```

`DJANGO_SECRET_KEY` 在生产环境必填；开发环境未设置时会生成临时密钥（重启失效）。
配置样例见各组件目录下的 `.env.example`，**禁止提交 `.env`**。

## 4. 常用命令

```bash
make help             # 查看全部命令
make backend-check    # Django 配置检查
make backend-test     # 后端测试
make agent-test       # Agent 单元测试
make web-build        # 前端构建（含 tsc 类型检查）
make lint             # 全量静态检查（ruff + gofmt + go vet + tsc）
```

## 5. 错误处理策略

- 后端：业务异常继承 `AppError` 并携带错误码，由 DRF 异常处理器统一转换为 `{error:{code,message,details,request_id}}`。
- Agent：错误码（如 `INVALID_ARGUMENT`、`LIBVIRT_UNAVAILABLE`）集中映射为 HTTP 状态，响应体为 `{code,message,request_id}`。
- 前端：统一在 `src/api/` 解析错误码，展示可读信息、错误码与 request_id，不展示堆栈。
- 错误码与状态码对照见 docs/ARCHITECTURE.md 第 5.5 节；分页、request_id 等统一约定见第 5.4 节。

## 6. 已知限制

- 真实创建/启动/删除虚拟机的端到端验收尚未执行（NOT VERIFIED）：libvirt 域生命周期已单独实测通过，业务链路待阶段 3 完成后验证。
- 前端已提供统一管理员/用户控制台、真实数据总览、虚拟机列表与详情、五步创建向导、节点/存储/网络/任务/审计页面。实施说明见 [docs/CONSOLE_UI_IMPLEMENTATION.md](docs/CONSOLE_UI_IMPLEMENTATION.md)。
- 备份恢复、TLS/mTLS、监控告警等生产化能力属于后续阶段。

## 7. 许可证

内部项目，暂未对外授权。
