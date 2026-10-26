# CloudVirt 环境与部署基线

- 版本：1.0（草案）　日期：2026-10-26
- 上游：《手册》第 2、3、17、18 章；实现任务见 IMPLEMENTATION_TASKBOOK.md 模块 A / O / P
- 约定：所有版本、端口、容量数值在实测前标 **TBD(待实测回填)**，禁止凭空填写。

## 1. 环境基线

### 1.1 开发机实测（2026-10-26）

| 项 | 实测 | 说明 |
| --- | --- | --- |
| OS | Ubuntu 26.04.1 LTS | 与目标环境一致 |
| Python | 3.14.4 | 后端运行时 |
| Node / npm | v24.22.1 / 12.2.1 | 前端构建 |
| Go | 1.26.8（阶段 1 已安装） | 模块 D 前置已解除 |
| PostgreSQL | 18.6 已安装并运行，专用账户与库 `cloudvirt` 已建立 | 迁移已执行；生产实例仍待规划 |
| /dev/kvm、virsh | 不存在 / 未安装 | 真实 KVM 验收仍 BLOCKED（容器环境无硬件虚拟化） |

### 1.2 目标宿主机要求

- Ubuntu Server LTS；CPU 支持硬件虚拟化并在固件中开启；存在 `/dev/kvm`；
- 软件包：`qemu-kvm`、`libvirt-daemon-system`、`libvirt-clients`、`qemu-utils`；
- `virsh -c qemu:///system list --all` 退出码为 0；
- 与管理后端之间管理网可达，且 Agent 端口仅允许后端来源访问。

## 2. 依赖与锁定

| 组件 | 清单文件 | 锁文件 | 安装命令（待实测确认） |
| --- | --- | --- | --- |
| 后端 | `apps/management/requirements/{base,dev,prod}.txt` | requirements 即锁定（`==`） | `make backend-install` |
| Agent | `services/virt-node-agent/go.mod` | 无外部依赖，暂无 go.sum | `make agent-build` |
| 前端 | `apps/web/package.json` | `package-lock.json` | `make web-install`（前端工程待建） |
| 宿主机 | `deploy/ansible/` | — | 待阶段 1 补齐（TBD） |

已实测锁定的版本（2026-10-26）：Django 6.1.2、djangorestframework 3.18.3、psycopg[binary] 3.3.6、gunicorn 26.2.0、ruff 0.17.2、Go 1.26.8、PostgreSQL 18.6、qemu-utils 10.2.1。

## 3. 环境变量

### 3.1 管理后端

| 变量 | 默认值建议 | 说明 |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | 无（必填） | 长随机值，密钥管理注入 |
| `DJANGO_DEBUG` | `false` | 生产必须为 false |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | 可信主机白名单 |
| `DATABASE_URL` | 占位连接串 | 专用应用账户，禁止超级用户 |
| `AGENT_SHARED_TOKEN` | 无（必填） | ≥32 随机字节，与 Agent 一致 |
| `CORS_ALLOWED_ORIGINS` | `http://127.0.0.1:5173` | 前端来源 |
| `NODE_OFFLINE_AFTER_SECONDS` | TBD | 节点离线判定阈值（可配置） |
| `AGENT_REQUEST_TIMEOUT_SECONDS` | TBD | 调用 Agent 超时 |

### 3.2 节点 Agent

| 变量 | 默认值建议 | 说明 |
| --- | --- | --- |
| `CLOUDVIRT_AGENT_LISTEN` | `127.0.0.1:9100` | 本机地址；跨机部署需显式绑定管理网 IP 并用防火墙限制来源 |
| `CLOUDVIRT_AGENT_TOKEN` | 无（必填） | ≥32 随机字节 |
| `CLOUDVIRT_IMAGE_DIR` | `/var/lib/cloudvirt/images` | 镜像根目录 |
| `CLOUDVIRT_DISK_DIR` | `/var/lib/cloudvirt/disks` | 磁盘根目录 |
| `CLOUDVIRT_MAX_REQUEST_SECONDS` | `120` | 单请求上限 |
| `CLOUDVIRT_ALLOW_DESTRUCTIVE` | `false` | 宿主机侧额外开关，**不能绕过后端权限** |

### 3.3 前端

| 变量 | 默认值建议 | 说明 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api/v1` | API 前缀 |
| `VITE_POLL_INTERVAL_MS` | TBD | 任务轮询间隔（页面离开必须清理） |

- 禁止把 `.env` 入库；`.env.example` 仅含占位值；日志中禁止打印 Token、密码、完整连接串。
- Token 轮换：采用“双 Token 兼容窗口 → 灰度切换 → 撤销旧 Token”的流程，并在文档中记录轮换时间与影响面。

## 4. 目录与权限规划

| 路径 | 用途 | 属主建议 | 备注 |
| --- | --- | --- | --- |
| `/var/lib/cloudvirt/images` | 镜像（ISO/QCOW2） | Agent 运行用户 | 独立文件系统或独立分区更佳 |
| `/var/lib/cloudvirt/disks` | 虚拟磁盘 | Agent 运行用户 | 需容量规划与安全余量 |
| `/var/log/cloudvirt` | 日志（后端/Agent） | 各自运行用户 | 滚动与保留策略 |
| PostgreSQL 数据目录 | 数据库 | postgres | 不与应用同盘最佳实践 |
| 备份目录 | 备份集 | 备份账户 | 独立于系统盘的受控位置 |

- 所有破坏性清理（删盘、undefine 域、清目录）必须有权限校验、二次确认或后端保护、审计记录与防误删检查。

## 5. 本地开发启动顺序（待实测回填命令）

```bash
# 1) 数据库（开发用）
cd deploy/compose && docker compose up -d postgres && pg_isready

# 2) 管理后端
cd apps/management && python manage.py migrate && python manage.py runserver 127.0.0.1:8000
# 另起终端：任务 worker
cd apps/management && python manage.py run_worker     # 命令名以实现为准（TBD）

# 3) 节点 Agent（需在具备 libvirt 的环境；开发机当前 BLOCKED）
cd services/virt-node-agent && go run ./cmd/virt-node-agent

# 4) 前端
cd apps/web && npm ci && npm run dev

# 5) 健康检查
curl -fsS http://127.0.0.1:8000/api/v1/health
curl -fsS http://127.0.0.1:9100/health
```

## 6. 宿主机初始化（Ansible / 手工）

```bash
sudo apt update
sudo apt install -y qemu-kvm libvirt-daemon-system libvirt-clients qemu-utils
sudo systemctl enable --now libvirtd
test -e /dev/kvm
virsh -c qemu:///system list --all
```

- 若 `/dev/kvm` 不存在，初始化脚本必须给出可读错误并以非 0 退出，**不得继续声称 KVM 已可用**。
- 部署前检查脚本：`scripts/precheck.sh`（OS 版本、CPU 虚拟化标志、`/dev/kvm`、libvirt 状态、磁盘空间、端口占用）。

## 7. 服务部署

| 组件 | 单元 | 要点 |
| --- | --- | --- |
| 管理后端 | `deploy/systemd/cloudvirt-management.service` | 非 root 运行、`Restart=always`、环境变量经 `EnvironmentFile`（文件权限 0600）、日志落 `/var/log/cloudvirt` |
| 任务 worker | `deploy/systemd/cloudvirt-worker.service` | 与后端同版本发布，独立进程 |
| 节点 Agent | `deploy/systemd/cloudvirt-agent.service` | 仅监听管理网/本机；如需 root 权限访问 libvirt 必须说明并最小化 |

- 生产部署必须验证：系统重启后服务自动恢复、健康检查通过、Agent 端口仅对后端可达。
- 管理端启用 HTTPS、安全 Cookie、CSRF/CORS 与可信主机策略；Django Debug 关闭。

## 8. 备份、恢复与升级（阶段 6）

| 项 | 要求 |
| --- | --- |
| 数据库备份 | 官方或已验证工具；独立于系统盘的受控位置；定义保留周期、加密与访问权限 |
| 恢复演练 | **必须演练**；仅有备份文件不算完成 |
| 虚拟机备份 | 明确关机备份或一致性快照、包含范围（磁盘/配置/EFI-NVRAM/元数据）、容量、校验、恢复目标与 UUID/网络冲突处理 |
| 升级 | 升级前备份数据库与配置；记录应用版本、迁移版本、Agent 版本；检测 Agent 与后端 API 兼容性 |
| 回滚 | 应用版本可回退；不可逆迁移必须有单独恢复计划，不得假设 `migrate` 总能安全逆转 |

## 9. 当前 BLOCKED 项（需负责人落实）

| 项 | 影响 | 建议动作 |
| --- | --- | --- |
| 无 KVM 宿主机 | 阶段 3/5/6 真实验收 | 指定测试宿主机并开通管理网访问（仍未解除） |
| ~~Go 工具链未安装~~ | ~~模块 D 无法开工~~ | 已解除：Go 1.26.8 已安装并写入依赖基线 |
| ~~PostgreSQL 未就绪~~ | ~~迁移与集成测试~~ | 已解除：本机 PG 18.6 + 专用账户/库，迁移已执行 |
| 备份目标位置未定 | 阶段 6 无法演练 | 确定备份存储与访问权限 |
