# CloudVirt 文档索引

- 文档版本：1.0（草案）
- 日期：2026-10-26
- 上游依据：`CloudVirt_逐模块开发实施手册.md`（下称《手册》）、`rule_py.md`、`rule_cpp.md`
- 适用范围：CloudVirt 云虚拟化管理平台（QEMU/KVM + libvirt + Go 节点 Agent + Django REST Framework + React 前端）

## 1. 文档清单

| 文档 | 作用 | 主要读者 |
| --- | --- | --- |
| README.md（本文件） | 文档导航、术语、维护约定 | 全体 |
| [console-media-workspace.md](./console-media-workspace.md) | 桌面与独立视频工作区、短期会话、多节点路由、媒体接入与真实联调记录 | 开发、运维、验收人员 |
| [IMPLEMENTATION_TASKBOOK.md](./IMPLEMENTATION_TASKBOOK.md) | **主执行文档**：基线审计结论 + 模块 A~P 逐模块任务卡 | 开发 Agent、开发/测试人员 |
| [ROADMAP.md](./ROADMAP.md) | 阶段 0~6 开发路线、里程碑、关键路径、门禁、风险登记 | 项目负责人、开发团队 |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 架构边界、目录结构、数据模型、状态机、API/错误码契约、ADR | 后端、Agent、前端开发 |
| [DATA_MODEL.md](./DATA_MODEL.md) | **字段级数据结构与数据库设计**：枚举字典、逐表字段/类型/约束/索引、ER、并发与保留策略 | 后端、数据库 |
| [TEST_ACCEPTANCE_PLAN.md](./TEST_ACCEPTANCE_PLAN.md) | 测试策略、验收矩阵、真实 KVM 验收清单、发布阻断项、记录模板 | 开发、测试、验收人员 |
| [FRONTEND_UX_SPEC.md](./FRONTEND_UX_SPEC.md) | 前端路由、全局布局、逐页线框、组件与状态语义、交互流程 | 前端、设计 |
| [RBAC_AND_SETTINGS.md](./RBAC_AND_SETTINGS.md) | 角色、权限码与权限矩阵、对象级授权、密码会话策略、用户管理、系统设置项 | 后端、前端、运维 |
| [ENVIRONMENT_DEPLOYMENT.md](./ENVIRONMENT_DEPLOYMENT.md) | 依赖基线、配置与环境变量、启动命令、宿主机初始化、部署与备份 | 开发、运维 |

## 2. 阅读顺序

1. 本文件：了解文档结构与术语。
2. ROADMAP.md：明确当前处于哪个阶段、本阶段交付什么、退出条件是什么。
3. IMPLEMENTATION_TASKBOOK.md：领取任务，按任务卡执行（一次只领一张卡）。
4. ARCHITECTURE.md + DATA_MODEL.md：实现前确认目录、库表字段、接口、状态机，避免重复造轮子。
5. CODING_STANDARDS.md：编码、提交、CI 门禁要求。
6. TEST_ACCEPTANCE_PLAN.md：写完代码后按此补测试与验收记录。
7. ENVIRONMENT_DEPLOYMENT.md：搭建环境、部署、备份与回滚。

## 3. 术语与缩写

| 术语 | 含义 |
| --- | --- |
| 管理后端 / Backend | Django + DRF 服务，业务状态来源，对外提供 /api/v1/ |
| 节点 Agent / Agent | 运行在 KVM 宿主机上的 Go 服务，执行受限虚拟化操作 |
| 节点 / Node | 一台运行 libvirt/QEMU 的 KVM 宿主机 |
| 实例 / Instance | 平台登记的虚拟机记录（数据库侧事实） |
| 域 / Domain | libvirt 中的虚拟机定义（宿主机侧事实） |
| 镜像 / Image | ISO/QCOW2 等源文件，登记于平台镜像目录 |
| 磁盘 / Disk | 实例虚拟磁盘文件（MVP 默认 QCOW2） |
| 期望状态 / desired_state | 用户希望实例处于的状态 |
| 观测状态 / observed_state | 从 libvirt 实际查询到的状态 |
| 任务状态 / operation_status | 当前异步任务的执行阶段 |
| 预留 / Reservation | 创建实例时预先占用的 CPU/内存/存储额度 |
| 对账 / Reconciliation | 数据库状态与 libvirt/磁盘实际状态的周期性比对 |

## 4. 文档状态标记

全文统一使用以下标记，禁止含糊表述：

| 标记 | 含义 |
| --- | --- |
| NEW | 尚未实现，本次需新增 |
| EXISTS-KEEP | 已实现且测试通过，保留 |
| EXISTS-FIX | 已实现但需修复 |
| BLOCKED | 依赖外部环境（KVM 宿主机、PostgreSQL、网络等），当前无法完成 |
| NOT VERIFIED | 代码已生成但未经该层级测试或真实验证，不得宣称通过 |
| TBD(待实测回填) | 数值/版本需在实际安装后确认，不得凭空填写 |

## 5. 维护约定

- 《手册》是需求与验收的唯一上游；本目录文档是实现映射，任何冲突以《手册》为准，并在本文档中记录偏差原因。
- 每个模块完成后必须回填：IMPLEMENTATION_TASKBOOK.md 的模块状态、ROADMAP.md 的阶段进度、涉及的接口变更（ARCHITECTURE.md）。
- 文档中禁止出现真实密钥、Token、口令、内网主机实名；仅记录配置项名称与注入方式。
- 涉及版本号、端口、容量的具体数值，实测前一律标 TBD(待实测回填)。
