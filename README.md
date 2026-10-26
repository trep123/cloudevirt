# CloudVirt 云虚拟化管理平台

基于 QEMU/KVM + libvirt 的云虚拟化管理平台：Go 节点 Agent 负责宿主机受限操作，Django + DRF 管理后端负责任务编排与状态管理，React + TypeScript 前端提供操作界面。

- 当前阶段：阶段 1（基础工程）骨架已完成并验证，阶段 2 起逐步实现业务模块
- 文档入口：[docs/README.md](./docs/README.md)
- 状态说明：功能是否验证通过以 docs 中的验收记录为准，未验证项一律标记 NOT VERIFIED

## 1. 组件

| 目录 | 组件 | 技术栈 | 职责 |
| --- | --- | --- | --- |
| `apps/management` | 管理后端 | Python 3.14 / Django 6.1 / DRF 3.18 | 认证授权、参数校验、调度与资源预留、任务编排、审计 |
| `services/virt-node-agent` | 节点 Agent | Go 1.26 | 宿主机上的受限虚拟化操作、资源采集、结构化错误 |
| `apps/web` | 前端 | React + TypeScript + Vite | 页面展示、表单交互、任务轮询、危险操作确认（建设中） |
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

宿主机侧还需 `qemu-kvm`、`libvirt-daemon-system`、`libvirt-clients` 与可用的 `/dev/kvm`。
当前开发容器**不具备 KVM**，`bash scripts/precheck.sh` 会以退出码 1 明确报告；真实虚拟机验收必须在具备 KVM 的宿主机执行。

## 3. 快速开始

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

# 5) 部署前检查
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
make lint             # 全量静态检查（ruff + gofmt + go vet）
```

## 5. 错误处理策略

- 后端：业务异常继承 `AppError` 并携带错误码，由 DRF 异常处理器统一转换为 `{error:{code,message,details,request_id}}`。
- Agent：错误码（如 `INVALID_ARGUMENT`、`LIBVIRT_UNAVAILABLE`）集中映射为 HTTP 状态，响应体为 `{code,message,request_id}`。
- 前端：统一在 `src/api/` 解析错误码，展示可读信息、错误码与 request_id，不展示堆栈。
- 错误码与状态码对照见 docs/ARCHITECTURE.md 第 5.4 节。

## 6. 已知限制

- 开发容器无 `/dev/kvm` 与 libvirt：真实创建/启动/删除虚拟机的验收尚未执行（NOT VERIFIED）。
- 前端工程与业务模块（节点、镜像、实例、任务、权限）尚未实现，当前仅后端与 Agent 骨架可用。
- 备份恢复、TLS/mTLS、监控告警等生产化能力属于后续阶段。

## 7. 许可证

内部项目，暂未对外授权。
