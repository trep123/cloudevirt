# CloudVirt 测试与验收计划

- 版本：1.0（草案）　日期：2026-10-26
- 上游：《手册》第 19 章；模块任务见 IMPLEMENTATION_TASKBOOK.md；环境与命令见 ENVIRONMENT_DEPLOYMENT.md
- 原则：**区分静态检查、单元测试、集成测试、真实 KVM 验收**；未做的层级一律标 NOT VERIFIED，不得描述为通过。

## 1. 测试层级与目录

| 层级 | 内容 | 位置 | 依赖外部资源 |
| --- | --- | --- | --- |
| 单元测试 | 模型校验、序列化器、权限逻辑、状态映射、参数校验、错误映射、路径校验、前端表单与 API 错误处理 | 后端 `apps/*/tests/`；Agent `*_test.go`；前端 `*.test.ts` | 无（mock / tmp 目录） |
| 集成测试 | Django + PostgreSQL 全流程；后端 ↔ Agent 契约；Agent ↔ libvirt | 后端 `tests/integration/`；Agent `internal/**/integration_test.go`（build tag） | PostgreSQL、（libvirt） |
| 端到端 / 真实验收 | 真实 KVM 宿主机上的创建、启动、关机、强停、删除、重启 Agent、重启 libvirt、断网、磁盘不足、后端重启恢复 | `docs/` 记录 + `scripts/` 辅助 | KVM 宿主机 + Agent |

- 覆盖率要求：核心逻辑（状态机、权限、资源预留、路径校验、任务领取/重试）行覆盖率 ≥ 80%。
- 测试禁止相互依赖执行顺序；禁止固定 `sleep`；临时文件用 `tmp_path` / `t.TempDir()`。

## 2. 各模块必备用例

| 模块 | 必备用例 |
| --- | --- |
| A | precheck 在无 KVM 环境退出码与输出；`.env.example` 无真实凭据；systemd 模板语法；启停脚本幂等 |
| B | 未认证 401；Viewer 创建 403；Operator 越权删除 403；Admin 通过；审计四要素齐全；伪造 user_id 无效 |
| C | 失败未达阈值不离线；达阈值 OFFLINE；恢复回 ONLINE/DEGRADED；MAINTENANCE 不被自动改写；离线节点拒创建；资源含采样时间与过期标记 |
| D | 配置缺失/Token 过短启动失败；无 Token 与错 Token 401；非法字段 400；libvirt 不可用 503；超时结束上下文；路径穿越/符号链接/相对路径被拒 |
| E | 正常 ISO/QCOW2 登记成功；扩展名与真实格式不符被拒；SHA-256 一致；越界路径被拒；被引用镜像删除 409；空间不足不留“READY 但文件不存在” |
| F | 磁盘创建后 qemu-img info 复核；空间不足被拒；路径越界被拒；删除时被引用拒绝；库写失败产生补偿/孤儿记录；孤儿扫描报告准确 |
| G | libvirt 状态全覆盖映射（含未知 → UNKNOWN）；并发状态更新不互相覆盖；进行中操作返回 409 |
| H | 合法请求返回 202 与任务 ID；轮询至 SUCCEEDED；资源预留并发不超分；镜像缺失/节点离线/资源不足分别失败；重复请求幂等 |
| I | 已运行启动幂等；ACPI 超时不自动强停；强停需权限与审计；删除三种行为（留盘/删域留盘/彻底删除）；失败可恢复 |
| J | 多 worker 不重复领取；不可重试错误一次性失败；可重试错误退避重试；重启后 PENDING 重排队、CREATING 先查 libvirt；幂等键重复提交不产生第二实例 |
| K | `npm ci` 与 `npm run build` 通过；401 跳转；任务轮询与页面离开清理；危险操作确认对话框；错误展示含任务 ID |
| L | 错误结构统一；分页与 page size 上限；日志字段完整且无敏感信息 |
| M | 白名单外网络被拒；被引用网络不可删；网络不可用时创建被拒 |
| N | 对账发现注入的孤儿域/孤儿磁盘；采集失败不误报 0；告警在仪表盘可见 |
| O | 威胁测试逐项（伪造 Token、路径穿越、特殊字符注入、越权、重放删除、并发超分、错误探测、直连 Agent 端口） |
| P | 数据库备份 + **恢复演练**；升级/回滚 runbook 演练；未实现能力前端不显示成功 |

## 3. 集成测试策略

1. **后端 + PostgreSQL**：建库、跑迁移、用真实 ORM 覆盖创建/任务/预留/对账路径。
2. **后端 ↔ Agent**：以契约测试固定请求/响应结构（建议使用可复用的 HTTP 桩或契约样例文件），覆盖 401/400/409/503/504 各分支。
3. **Agent ↔ libvirt**：使用真实 libvirt 连接（测试优先使用 `qemu:///system` 的测试域命名前缀），**不得只用 mock 代替全部验收**。
4. **并发与竞态**：资源预留、任务领取、同实例并发操作必须有并发用例（可用多线程/多进程或数据库并发事务模拟）。

## 4. 真实宿主机验收清单（阶段 3 起）

前置条件：Ubuntu Server LTS 物理机或支持嵌套虚拟化的宿主机；`qemu-kvm`、`libvirt-daemon-system`、`libvirt-clients`、`qemu-utils` 已安装；`/dev/kvm` 存在；`virsh -c qemu:///system list --all` 返回 0；Agent 与管理后端网络互通且端口受限。

| 序号 | 场景 | 关键命令 / 操作 | 预期 |
| --- | --- | --- | --- |
| 1 | 环境自检 | `test -e /dev/kvm`；`virsh -c qemu:///system list --all` | 退出码 0，可连接系统 libvirt |
| 2 | 创建并启动 | 前端/API 创建 → 轮询任务 | 任务 SUCCEEDED；`virsh list` 可见域 |
| 3 | 规格核对 | `virsh dominfo <domain>` | CPU/内存/UUID 与数据库一致 |
| 4 | 磁盘核对 | `qemu-img info <disk>` | 格式 QCOW2、容量与请求一致、路径在允许目录 |
| 5 | 正常关机 | API shutdown | 域状态 SHUTOFF，任务 SUCCEEDED |
| 6 | 强制停止（仅测试环境） | API force-stop | 域停止，有审计与二次确认记录 |
| 7 | 删除 | DELETE（分别测留盘与彻底删除） | 域销毁；磁盘按选择保留/删除；数据库一致 |
| 8 | Agent 重启 | systemctl restart | 节点转 OFFLINE 后恢复 ONLINE，实例状态对账正确 |
| 9 | libvirt 重启 | systemctl restart libvirtd | Agent 返回稳定错误码，恢复后对账收敛 |
| 10 | 网络中断 | 断开管理网 | 失败计数累加，超阈值 OFFLINE，恢复后自动同步 |
| 11 | 磁盘不足 | 填充或配额限制 | 创建失败并说明资源类型，不留脏记录 |
| 12 | 后端重启 | 重启 Django 与 worker | 长期 PENDING 重排队，CREATING 先查 libvirt 后决策 |

- 开发机当前**无 KVM / 无 Go / 无 PostgreSQL**：上述 1~12 在本机标记 **BLOCKED**，必须在目标宿主机执行并留存输出。

## 5. 验收矩阵（模块 × 层级）

| 模块 | 单测 | 集成 | 真实 KVM | 故障注入 | 安全 |
| --- | --- | --- | --- | --- | --- |
| A | ● | — | 环境自检 | — | 密钥扫描 |
| B | ● | ● | — | 权限失效 | 越权、伪造身份 |
| C | ● | ● | ●（Agent 停启） | 超时/401/格式错 | 端口限制 |
| D | ● | ● | ● | libvirt 不可用、超时 | Token、路径穿越 |
| E | ● | ● | ● | 空间不足、格式错 | 越权路径、覆盖在用镜像 |
| F | ● | ● | ● | qemu-img 失败 | 路径越界、误删 |
| G | ● | ● | ● | 未知状态、并发 | — |
| H | ● | ● | ● | 节点离线/镜像缺失/资源不足/超时 | 并发超分、注入 |
| I | ● | ● | ● | ACPI 超时、删除中断 | 强停/删除重放 |
| J | ● | ● | ●（后端重启） | worker 崩溃、DB 中断 | 幂等键重放 |
| K | ● | — | — | 401、任务失败展示 | 会话失效 |
| L | ● | ● | — | — | 错误信息不泄露 |
| M | ● | ● | ● | 网络不可用 | 非白名单接入 |
| N | ● | ● | ● | 孤儿域/孤儿磁盘注入 | — |
| O | ● | ● | ● | 威胁测试逐项 | 全部威胁项 |
| P | ● | ● | ● | 恢复演练 | 备份权限 |

## 6. 发布阻断项（任一未通过不得标记“可生产使用”）

- [ ] 未授权用户可以执行虚拟机操作
- [ ] Agent 可被公网任意访问
- [ ] 删除操作可能误删不相关磁盘
- [ ] 任务超时会导致重复创建或错误释放资源
- [ ] 数据库状态与 libvirt 状态无法对账
- [ ] 没有数据库备份或恢复演练
- [ ] 没有真实 KVM 集成测试
- [ ] 密钥硬编码在仓库
- [ ] 生产部署仍开启 Django Debug
- [ ] 资源预留缺失导致并发超分
- [ ] 危险操作（强停、彻底删除）无二次确认与审计
- [ ] 孤儿资源处理默认自动删除（应为报告优先）

## 7. 验收记录模板（每模块/每场景一份）

```text
模块 / 场景：
提交版本（Commit）：
测试环境（OS / 是否 KVM / 组件版本）：
执行人 / 执行时间：
前置条件：
测试命令：
实际输出（关键片段）：
预期输出：
结果：PASS / FAIL / BLOCKED / NOT VERIFIED
失败日志：
已知限制：
回滚方式：
```

## 8. 静态检查与构建基线命令

```bash
# Go Agent
cd services/virt-node-agent && gofmt -l . && go vet ./... && go test ./...

# Django 后端
cd apps/management && python manage.py check && \
  python manage.py makemigrations --check --dry-run && python manage.py test

# 前端
cd apps/web && npm ci && npm run build

# 数据库与 KVM（真实环境）
pg_isready; test -e /dev/kvm; virsh -c qemu:///system list --all
```

- 上述命令的输出与退出码必须原样记录；安装/依赖超时不得记为“构建失败”，也不得把未成功构建描述为通过。
