# CloudVirt 实施任务书（Agent 可执行版）

- 版本：1.0（草案）　日期：2026-10-26
- 上游：《CloudVirt_逐模块开发实施手册.md》第 0、21 章；编码规范见 docs/CODING_STANDARDS.md；目录与接口见 docs/ARCHITECTURE.md
- 使用方式：一次只领取一张任务卡；**先复验现状 → 先补测试 → 再改代码 → 跑命令 → 回填状态**。

## 1. 基线审计结论（阶段 0 交付）

### 1.1 仓库现状（2026-10-26 实测）

| 检查项 | 实测结果 |
| --- | --- |
| 分支 / 提交 | master / 73e4440 “first commit” |
| 工作区 | 3 个未跟踪文件（手册、rule_cpp.md、rule_py.md），无用户未提交的代码修改 |
| README.md | 存在但内容为空（1 行），需在阶段 1 补齐 |
| 应用代码 | 无：无后端、无 Agent、无前端、无依赖清单、无迁移、无测试 |
| 《手册》0.2 示例目录 | 均不存在（apps/、services/、deploy/ 需新建），无命名冲突 |

### 1.2 工具链实测（开发机）

| 组件 | 实测 | 约束 |
| --- | --- | --- |
| 操作系统 | Ubuntu 26.04.1 LTS | 与目标环境一致，可直接开发 |
| Python | 3.14.4 | 后端基线；Django/DRF 版本在安装时确认兼容性，标 TBD(待实测回填) |
| Node / npm | v24.22.1 / 12.2.1 | 前端基线可用 |
| Go | 未安装 | 模块 D 开工前安装并锁定版本，标 TBD(待实测回填) |
| PostgreSQL | 客户端与服务均未就绪 | 迁移与集成测试当前 BLOCKED |
| /dev/kvm、virsh | 不存在 / 未安装 | 真实 KVM 验收当前 BLOCKED，须在独立宿主机执行 |

### 1.3 审计结论

1. 模块 A~P 全部为 NEW；不存在重复实现风险，也无既有代码需要兼容。
2. 目录按 docs/ARCHITECTURE.md 第 2 章新建；模块推进中若发现与文档不一致，以代码为准并回改文档。
3. 阶段 3/5/6 的真实环境验收依赖独立 KVM 宿主机与 PostgreSQL 实例；未落实前一律标记 BLOCKED / NOT VERIFIED。
4. 每完成一张卡，必须回填：本文件第 2 章状态表、docs/ROADMAP.md 阶段进度、涉及的接口变更（ARCHITECTURE.md）。

## 2. 模块状态总表

| 编号 | 模块 | 状态 | 目标阶段 | 前置依赖 | 关键阻塞 | 主要落地位置 |
| --- | --- | --- | --- | --- | --- | --- |
| A | 基础工程与部署配置 | NEW→部分完成（2026-10-26） | 阶段 1 | 无 | Ansible 初始化待补；前端工程待建 | 全仓 |
| B | 用户认证、角色和授权 | NEW | 阶段 1（完善于 4） | A | 无 | 后端 accounts、前端登录 |
| C | 节点管理与心跳 | NEW | 阶段 2 | A、D | Agent 可达 | 后端 nodes、Agent host |
| D | Go 节点 Agent | NEW | 阶段 2 | A | Go 工具链、libvirt 开发库 | services/virt-node-agent |
| E | 镜像管理 | NEW | 阶段 3 | A、B、D | 镜像目录、qemu-img | 后端 images、Agent storage |
| F | 存储与虚拟磁盘 | NEW | 阶段 3 | D、E | 磁盘目录与容量 | 后端 instances、Agent storage |
| G | 实例模型与状态机 | NEW | 阶段 3 | A | 无 | 后端 instances |
| H | 虚拟机创建 | NEW | 阶段 3 | C、D、E、F、G、J | 真实 KVM（验收） | 后端 + Agent + 前端 |
| I | 生命周期操作 | NEW | 阶段 3 | G、H、J | 真实 KVM（验收） | 后端 + Agent + 前端 |
| J | 任务队列、幂等与恢复 | NEW | 阶段 2（完善于 4） | A | 无 | 后端 tasks |
| K | 前端页面与 API 客户端 | NEW | 阶段 2（完善于 3） | B、L | 无 | apps/web |
| L | API 统一规范 | NEW | 阶段 1 | A | 无 | 后端 common |
| M | 网络管理 | NEW | 阶段 3（完善于 5） | D | libvirt 网络 / 网桥 | 后端 networks、Agent |
| N | 监控、对账和告警 | NEW | 阶段 4（完善于 6） | C、J | 无 | 后端 monitoring |
| O | 安全加固 | NEW | 阶段 4 | B、D、L | 生产环境（验收） | 全栈 |
| P | 备份、恢复与升级 | NEW | 阶段 6 | 全部 | 备份目标位置 | 运维 + 文档 |

## 3. 逐模块任务卡

### 模块 A：基础工程与部署配置（NEW / 阶段 1）

- **目标**：新环境可复现安装；后端、Agent、前端可独立启停；健康检查可明确报告状态。
- **现状**：无依赖清单、无配置样例、无启停命令、无部署单元、无部署前检查；README 为空。
- **范围**：依赖清单与锁文件、`.env.example`、启停与测试命令、systemd 模板、compose 开发库、部署前检查脚本、目录与权限规划。**不含**：任何业务功能。
- **文件改动**：
  1. `README.md`：项目简介、依赖要求、启动/测试/构建命令、错误处理策略（补齐空文件）
  2. `apps/management/requirements/`（base/dev/prod）+ 锁文件；`services/virt-node-agent/go.mod`；`apps/web/package.json` + 锁文件
  3. `apps/management/.env.example`、`services/virt-node-agent/.env.example`、`apps/web/.env.example`（仅占位值）
  4. `deploy/systemd/*.service`、`deploy/compose/docker-compose.yml`、`deploy/ansible/`（KVM 初始化）
  5. `scripts/precheck.sh`（OS 版本、CPU 虚拟化标志、`/dev/kvm`、libvirt 状态、磁盘空间、端口占用）
  6. `Makefile`（`dev-up` / `test` / `build` / `lint` 统一入口）
- **接口**：后端 `GET /api/v1/health`；Agent `GET /health` → `{"status":"ok","version":"x.y.z"}`。
- **关键规则**：`.env` 不入库；锁文件必须提交；数据/日志/镜像/磁盘分目录并定义属主与容量规划；数据库使用专用账户，禁止超级用户。
- **异常场景**：`/dev/kvm` 缺失 → 输出可读错误并以非 0 退出，不得继续声称 KVM 可用；端口被占用 → 明确指出端口与进程来源。
- **测试用例**：precheck 在无 KVM 环境的退出码与输出；`.env.example` 不含真实凭据（密钥扫描）；systemd 单元语法检查；三组件启停脚本幂等。
- **执行命令**：见 docs/ENVIRONMENT_DEPLOYMENT.md 第 3、5 章。
- **验收标准**：全新目录按文档可启动至健康检查通过；三组件启停/测试/构建命令齐备且可执行；密钥扫描通过；生产部署需验证 systemd 重启后恢复。
- **回滚**：删除新增模板与脚本；此阶段无业务代码，回滚无数据影响。

### 模块 B：用户认证、角色和授权（NEW / 阶段 1，阶段 4 完善）

- **目标**：所有管理操作在后端完成认证与授权；前端隐藏按钮不作为权限边界。
- **现状**：无用户模型、无权限体系、无登录页。
- **文件改动**：`apps/management/apps/accounts/`（models、serializers、views、permissions、urls、management commands）、`config/settings.py`（DRF 默认认证/权限/限流）、迁移、`apps/web/src/api` 认证拦截与 401 跳转、登录页。
- **角色基线**：`Admin`（全局管理）、`Operator`（授权范围内创建/启动/关机/重启）、`Viewer`（只读）。**复用 Django Group + Permission，禁止另造权限系统**。
- **关键规则**：默认全局要求认证（白名单仅健康检查）；每个写操作显式权限检查；对象级授权；删除/强停/镜像替换写审计；未认证 401、无权限 403；认证失败不泄露用户名是否存在与内部堆栈；**禁止仅凭客户端提交的 user_id 判定身份**；首管理员创建受部署保护（一次性 bootstrap 管理命令），禁止开放无认证注册。
- **异常场景**：Token 过期/撤销；越权访问他人对象；并发登录失效；限流触发 429。
- **测试用例**：未认证访问实例列表 401；Viewer 创建实例 403；Operator 删除非授权实例 403；Admin 授权操作 200/202；审计事件含操作者、对象、结果、时间；伪造 user_id 无效。
- **执行命令**：`python manage.py test apps.accounts`、`pytest`（若采用）、前端 `npm run build`。
- **验收标准**：上述用例全绿；登录失效后前端清会话并跳转；权限矩阵与文档一致。
- **回滚**：迁移回滚 + 关闭新增权限校验开关（若引入）；保留审计数据不动。

### 模块 C：节点管理与心跳（NEW / 阶段 2）

- **目标**：登记节点、验证可达、展示资源、识别离线、恢复后重新同步。
- **现状**：无节点模型、无心跳、无 Agent 资源接口。
- **文件改动**：`apps/management/apps/nodes/`（models、serializers、views、heartbeat 任务、状态判定、客户端）、配置阈值、迁移、测试；Agent 侧 `internal/host`（采集）。
- **数据结构**：Node（name、endpoint、status、last_seen_at、last_error、consecutive_failures、cpu_total、memory_total_mib、memory_available_mib、storage_total_bytes、storage_free_bytes、agent_version、**资源采样时间**）。status ∈ UNKNOWN/ONLINE/DEGRADED/OFFLINE/MAINTENANCE。
- **Agent 契约**：`GET /health`；`GET /api/v1/node/resources`（cpu_logical、memory_total_mib、memory_available_mib、storage[]、sampled_at）。数值必须真实采集，禁止写死样例。
- **关键规则**：离线阈值可配置（`NODE_OFFLINE_AFTER_SECONDS`）；**单个采集字段失败不得把其他字段覆盖为 0**，保留上次值并标记过期；MAINTENANCE 不参与调度；离线节点拒收创建任务；恢复后先重新采集再做实例状态对账，再恢复调度资格。
- **异常场景**：Agent 超时、Agent 返回 401、资源响应格式错误、数据库暂时不可用、节点处于 MAINTENANCE。
- **测试用例**：失败未达阈值不离线；达阈值转 OFFLINE；恢复后回 ONLINE/DEGRADED；状态变更写日志与审计；离线节点创建被拒；资源展示含采样时间与过期标记。
- **验收标准**：单元测试全绿；**真实环境**停止/启动 Agent 后状态正确翻转（开发机无 KVM/Agent 时标记 NOT VERIFIED）。
- **回滚**：关闭心跳调度、回滚迁移；节点状态字段保留可空。

### 模块 D：Go 节点 Agent（NEW / 阶段 2）

- **目标**：提供受限、可测试、可观测的宿主机操作 API；未定义操作默认拒绝。
- **现状**：无 Go 工程，开发机 Go 未安装。
- **文件改动**：`services/virt-node-agent/`：`cmd/virt-node-agent/main.go`、`internal/{config,httpapi,auth,host,libvirt,storage,domainxml,audit}`、`go.mod`、`.env.example`、单元测试与集成测试。
- **关键规则**：`exec.CommandContext` + 参数数组 + context deadline；捕获 stdout/stderr/退出码/耗时；不接受调用方指定可执行文件路径或任意命令参数；对名称、UUID、磁盘路径、网络名分别校验；XML 使用编码器/安全转义，禁止拼接未转义字符串；删除/销毁前二次校验 UUID 与域名对应关系；Token 使用常量时间比较。
- **错误码**：UNAUTHORIZED 401 / INVALID_ARGUMENT 400 / NOT_FOUND 404 / CONFLICT 409 / INSUFFICIENT_RESOURCE 409 / LIBVIRT_UNAVAILABLE 503 / COMMAND_TIMEOUT 504 / OPERATION_FAILED 500 / INTERNAL_ERROR 500；统一响应 `{code,message,request_id}`。禁止回传堆栈、Token、敏感路径。
- **配置**：`CLOUDVIRT_AGENT_LISTEN`、`CLOUDVIRT_AGENT_TOKEN`、`CLOUDVIRT_IMAGE_DIR`、`CLOUDVIRT_DISK_DIR`、`CLOUDVIRT_MAX_REQUEST_SECONDS`、`CLOUDVIRT_ALLOW_DESTRUCTIVE`；Token 过短或缺失时启动失败。
- **异常场景**：libvirt 不可达、命令超时、路径越界/符号链接/目录穿越、并发同 UUID 创建、Token 错误。
- **测试用例**：配置缺失/Token 过短启动失败；无 Token 与错 Token 401；非法字段 400；libvirt 不可用返回稳定错误码；超时结束命令上下文；路径越界被拒。
- **执行命令**：`gofmt -l .`、`go vet ./...`、`go test ./...`。
- **验收标准**：单测与 vet 全绿；真实 libvirt 集成测试通过（开发机 BLOCKED → 在 KVM 宿主机执行并记录）。
- **回滚**：停止服务并回退二进制/版本；不涉及数据库。

### 模块 E：镜像管理（NEW / 阶段 3）

- **目标**：ISO/QCOW2 等镜像的登记、校验、存放、可用性检测与安全删除。
- **现状**：无模型、无上传接口、无校验流程。
- **文件改动**：`apps/management/apps/images/`（models、serializers、views、import 服务、校验器）、迁移、测试；Agent `internal/storage`（`qemu-img info` 与路径校验）；前端镜像列表与导入页。
- **数据结构**：Image（name、format、path（服务端生成）、size_bytes、checksum_sha256、status、os_family、os_version、created_by、时间戳）。status ∈ UPLOADING/VERIFYING/READY/FAILED/DELETING。
- **导入流程**：认证授权 → 限制大小与扩展名 → 服务端随机文件名写临时文件 → 流式 SHA-256（禁止整文件入内存）→ 检查真实文件类型（不得只看扩展名）→ QCOW2 调用 `qemu-img info` 复核 → 同文件系统原子重命名 → 写库并置 READY → 失败清理临时文件（清理失败生成告警）。
- **关键规则**：路径规范化后再次校验位于允许根目录；不跟随未校验的符号链接；禁止覆盖被实例使用的镜像；删除前检查引用，存在引用返回 409 IMAGE_IN_USE；限制大小/超时/并发。
- **异常场景**：扩展名与真实格式不符、SHA-256 不一致、磁盘不足、路径越界、被引用删除、清理失败。
- **验收标准**：正常 ISO/QCOW2 可登记；伪造扩展名被拒；校验和与文件一致；越界路径被拒；被引用镜像不可删；空间不足时不会留下“READY 但文件不存在”的记录。
- **回滚**：删除导入记录与文件（仅在确认无引用后），保留审计。

### 模块 F：存储与虚拟磁盘（NEW / 阶段 3）

- **目标**：统一磁盘创建、容量、依赖与删除，避免文件与数据库记录脱节。
- **现状**：无磁盘模型、无 qemu-img 调用封装。
- **文件改动**：`apps/management/apps/instances/`（disk model、disk service、孤儿扫描任务）、迁移、测试；Agent `internal/storage`（create/info/delete 与路径校验）；`scripts/` 孤儿扫描入口。
- **关键规则**：文件名由服务端生成（建议基于实例 UUID）；目录必须在配置的磁盘根目录下；创建前检查剩余空间与安全余量；`qemu-img create` 参数数组 + 超时；MVP 默认 QCOW2（raw 由配置决定）；创建后 `qemu-img info` 复核；**文件先成功、再推进数据库状态**，库写失败执行补偿清理或登记孤儿；删除前确认实例已停止、无其他域引用、路径通过根目录校验；不可恢复删除写审计。
- **孤儿扫描**：磁盘目录无库记录、库记录指向不存在文件、libvirt 域引用未登记磁盘、任务失败残留临时文件。**默认只出报告，未经配置与安全验证不得自动删除**。
- **异常场景**：空间不足、qemu-img 失败/超时、路径越界、删除时被引用、库写失败。
- **验收标准**：创建/复核/删除单测通过；孤儿扫描报告准确；删除不影响其他实例磁盘。
- **回滚**：保留补偿清理记录；删除操作失败进入可重试状态，不得丢失资源引用。

### 模块 G：虚拟机实例模型与状态机（NEW / 阶段 3）

- **目标**：明确区分期望状态、观测状态与任务状态，状态映射集中管理。
- **现状**：无实例模型。
- **文件改动**：`apps/management/apps/instances/`（models、state_machine.py 集中映射、serializers）、迁移、测试。
- **数据结构**：Instance（id、uuid、name、node_id、image_id、vcpu、memory_mib、disk_gib、autostart、desired_state、observed_state、operation_status、last_error_code/message、created_by、时间戳）。
- **状态**：observed ∈ SHUTOFF/RUNNING/PAUSED/CRASHED/UNKNOWN；operation ∈ PENDING/VALIDATING/PREPARING/CREATING/VERIFYING/SUCCEEDED/FAILED/CANCELLED/RECONCILING。**libvirt 未知状态一律映射 UNKNOWN，不得默认当作关机**。
- **关键规则**：用户操作先建任务再异步执行；状态更新用事务与条件更新防并发覆盖；同实例进行中操作返回 409 OPERATION_IN_PROGRESS 或按明确幂等策略合并；**API 接收时不得直接把观测状态置为 RUNNING**，必须查询 libvirt 后确认；节点离线时观测状态置为未知/过期，不能直接认为已关机。
- **异常场景**：并发操作、libvirt 返回未知状态、节点离线、状态回写失败。
- **验收标准**：状态映射单测覆盖全部 libvirt 状态与未知值；并发更新用例通过。
- **回滚**：迁移回滚；状态字段允许 UNKNOWN 兜底。

### 模块 H：虚拟机创建（NEW / 阶段 3，核心）

- **目标**：以异步任务方式完成实例创建，含资源预留、Agent 调用、失败补偿。
- **现状**：无创建接口、无调度、无资源预留。
- **文件改动**：后端 `instances/views.py`（POST /api/v1/instances/，202）、`instances/services/create.py`（校验、调度、预留）、`tasks/`（任务与执行器）、Agent `internal/{libvirt,domainxml,storage}`、前端创建表单与任务进度。
- **接口**：`POST /api/v1/instances/` → 202，返回 instance（observed_state=UNKNOWN、operation_status=PENDING）与 task（id、status、status_url）。
- **后端校验顺序**：认证 → `instance.create` 权限 → 名称字符集/长度/唯一性 → 节点存在且可调度、心跳未过期 → 镜像存在且 READY 且节点可访问 → vCPU/内存/磁盘为正整数且不超上限 → 读取带采样时间的资源（过期则刷新或拒调度）→ CPU/内存/存储与安全余量 → **同一事务**内创建实例 + 任务 + 资源预留 → 提交后由执行器调 Agent（禁止在事务内等待外部 HTTP）。
- **资源预留**：对节点资源加锁或等效并发控制；预留记录含 task_id、node_id、vcpu_reserved、memory_reserved_mib、disk_reserved_bytes、status；成功转已分配；失败且确认资源未创建/已清理后释放；周期对账识别差异。
- **Agent 创建流程**：Token 与字段校验 → 复核镜像/磁盘路径在允许根内 → 查同 UUID 域（存在则按幂等返回现状）→ 校验 libvirt 可用 → 创建/校验磁盘 → 生成 Domain XML（名称、UUID、内存、vCPU、磁盘、网卡、控制台；动态字段编码与校验）→ 定义/创建域 → 回查域信息核对 UUID/内存/vCPU/磁盘 → 返回结构化结果 → 失败返回稳定错误码并保留追踪信息。
- **Domain XML 约束**：名称由平台生成或校验，禁止任意 XML 片段；UUID 服务端生成；容量与请求一致；磁盘源路径来自已校验存储模块；网卡接入白名单网络；BIOS/UEFI、机器类型、磁盘总线集中配置；**生成后必须 XML 解析校验，失败不得调用 libvirt**；快照记录不得泄露敏感初始化数据。
- **失败补偿**：见《手册》10.6 表（校验失败不落资源；节点离线有限重试；资源不足 409；镜像缺失不建盘；XML 无效不调用；超时先查域；回写失败进对账；清理失败标记人工处理）。
- **验收**：合法请求得到任务 ID 并轮询至 SUCCEEDED；`virsh list --all`、`virsh dominfo` 核对 CPU/内存/UUID；磁盘格式容量路径核对；API 查询结果与 libvirt 一致；重复请求幂等；注入节点离线/镜像缺失/存储不足/libvirt 错误验证失败态与日志；删除测试实例后清理策略符合预期。
- **回滚**：清理顺序 = 域 → 磁盘 → 预留 → 记录；任一步失败保留失败记录并标记人工处理，不得声称已回滚。

### 模块 I：虚拟机生命周期操作（NEW / 阶段 3）

- **目标**：start / shutdown / force-stop / reboot / delete 的安全异步实现。
- **现状**：无操作路由、无 Agent 操作接口。
- **文件改动**：后端 `instances/views.py` 操作路由与 services、Agent `internal/libvirt` 操作封装、前端详情操作区与确认对话框。
- **接口**：`POST /api/v1/instances/{id}/start/`、`/shutdown/`、`/force-stop/`、`/reboot/`；`DELETE /api/v1/instances/{id}/`（参数显式声明是否删除磁盘）。
- **关键规则**：启动前查实际状态，已运行按幂等返回；关机发 ACPI 请求并设超时，**超时默认不自动强停**；强停等同断电，需更高权限 + 二次确认 + 审计；重启与强制重启分离命名与授权；进行中操作拒绝或合并，避免 start/shutdown/reboot 竞态；删除区分“注销实例”与“删除磁盘”，**默认不得隐式等同**；删除中失败进入可重试状态，不得丢失资源引用。
- **异常场景**：节点离线、libvirt 错误、ACPI 超时、域不存在、磁盘被引用、并发操作、删除中断。
- **验收**：保留磁盘删除 / 删域留盘 / 彻底删除三种行为均有测试；其他实例磁盘不受影响；任务失败可恢复；真实 KVM 环境跑通全序列（开发机 BLOCKED → NOT VERIFIED）。
- **回滚**：删除按任务补偿；强制停止不可回滚，须前置确认。

### 模块 J：任务队列、幂等性和恢复（NEW / 阶段 2，阶段 4 完善）

- **目标**：异步任务可靠执行、可重试、可恢复，且同一任务不被多个 worker 领取。
- **现状**：无任务模型、无 worker。
- **文件改动**：`apps/management/apps/tasks/`（models、executor/worker、retry 策略、idempotency、recovery）、管理命令入口、迁移、测试。
- **数据结构**：Task（id UUID、type、status、resource_type/resource_id、requested_by、idempotency_key、attempt_count、max_attempts、started_at/finished_at、last_error_code/message、时间戳）。
- **关键规则**：MVP 采用**数据库任务表 + 独立 worker 轮询**（不引入 Celery/RQ，避免多套任务系统）；领取用数据库锁或原子条件更新；仅对可恢复错误重试（网络抖动等），参数/权限/格式错误立即失败；有限次数 + 退避；重试前确认幂等；超限标记 FAILED 并保留上下文。
- **崩溃恢复**：重启后重新排队长期 PENDING；对长期 CREATING 先查 libvirt 再决定继续/成功/失败；过期预留确认无实际资源后才释放；**禁止把全部未结束任务简单标记失败**；所有恢复动作有可追踪日志。
- **异常场景**：worker 崩溃、DB 连接中断、Agent 长时间无响应、重复提交同一 idempotency_key。
- **验收**：并发 worker 不重复领取；不可重试错误一次性失败；服务重启后任务恢复到正确状态；幂等键重复提交不产生第二个实例。
- **回滚**：停止 worker；任务表数据保留用于审计。

### 模块 K：前端页面与 API 客户端（NEW / 阶段 2，阶段 3 完善）

- **目标**：MVP 页面齐备，API 调用集中、类型安全、错误可理解。
- **现状**：无前端工程。
- **文件改动**：`apps/web/`：`src/api/`（统一客户端、类型定义、错误解析、401 跳转）、`src/pages/`（登录、仪表盘、节点列表/详情、镜像列表/导入、实例列表、创建表单、实例详情、任务列表/详情、用户权限、系统设置与审计）、`src/components/`（确认对话框、状态标签、任务进度）。
- **页面清单**：登录、仪表盘、节点列表与详情、镜像列表与导入、虚拟机列表、创建虚拟机、虚拟机详情、任务列表与详情、用户/权限管理、系统设置与审计（可拆分）。
- **关键规则**：所有请求集中在 `src/api/`；统一 Base URL、认证、JSON 解析、超时、错误码与 401 跳转；TS 定义请求/响应类型，**禁止以 any 作为默认类型**；业务组件不得自拼 URL 或另写错误解析；创建返回任务 ID 后展示进度并轮询；页面离开清理轮询；状态不得只用颜色表达（需文字或图标）。
- **创建表单行为**：名称、节点、镜像、vCPU、内存、磁盘、是否开机自启（以后端实际支持为准）；节点切换刷新可用资源；镜像不可用禁止提交；前端即时提示、后端最终校验；提交期间禁用按钮；失败展示可读消息与任务 ID（禁止只显示“未知错误”）。
- **危险操作 UX**：强停与彻底删除必须确认对话框；删除对话框明确说明是否删除磁盘；失败时保留实例详情与错误信息。
- **验收**：`npm ci`（先审查并提交锁文件）与 `npm run build` 通过，记录真实输出与退出码；页面可完成主要流程；**未成功构建不得描述为通过**。
- **回滚**：前端独立部署，回滚到上一构建产物即可。

### 模块 L：API 统一规范（NEW / 阶段 1）

- **目标**：统一前缀、分页、错误结构、状态码、时间与文档。
- **现状**：无 API。
- **文件改动**：`apps/management/common/`（统一响应与异常转换、错误码枚举、分页类、request_id 中间件、结构化日志）、DRF 异常处理器、`docs/ARCHITECTURE.md` 接口索引同步。
- **规则**：JSON UTF-8；统一前缀 `/api/v1/`；时间 ISO 8601 UTC；列表分页且限制最大 page size；写操作使用正确 HTTP 方法；创建/操作接口支持幂等键或明确重复行为；文档描述认证、权限、字段、状态码、错误码。
- **错误响应**：`{error:{code,message,details,request_id}}`；**同一 API 不得混用多种错误结构**。
- **状态码**：200/201/202/400/401/403/404/409/413/429/500/503/504 按《手册》14.3 使用。
- **验收**：错误结构单测；列表分页与 page size 上限生效；日志字段完整且不含敏感信息。
- **回滚**：统一异常处理器可开关，回滚不影响已发布路由。

### 模块 M：网络管理（NEW / 阶段 3，阶段 5 完善）

- **目标**：MVP 仅支持一个经管理员验证的 libvirt 网络或 Linux Bridge；后续阶段扩展到多节点网络范围。
- **现状**：无网络模型、无白名单校验。
- **文件改动**：`apps/management/apps/networks/`（models、serializers、views、校验）、Agent `internal/libvirt`（网络查询与白名单校验）、前端展示。
- **规则**：记录网络名称、类型、桥接设备、VLAN（如支持）、状态、节点范围；Agent **只允许连接白名单网络**；创建实例前校验网络存在且可用；删除网络前检查是否被虚拟机引用；网络操作写审计。
- **安全边界**：管理网与业务网分离；Agent 端口仅允许管理后端访问；**禁止普通用户把虚拟机网卡接入宿主管理网桥**；VLAN/租户隔离必须真实网络测试；不得把“创建 Linux Bridge”视为完整租户隔离方案。
- **验收**：白名单外网络被拒；被引用网络不可删；创建实例时网络不可用被拒。
- **回滚**：网络配置回退；不影响已有域。

### 模块 N：监控、对账和告警（NEW / 阶段 4，阶段 6 完善）

- **目标**：资源可观测，数据库与 libvirt 状态可对账，异常可告警。
- **现状**：无采集、无对账、无告警。
- **文件改动**：`apps/management/apps/monitoring/`（采集、对账任务、差异记录、告警）、Agent `internal/host` 扩展、前端仪表盘告警区。
- **采集项**：CPU 逻辑核心与使用率（如支持）、总/可用内存、文件系统容量与剩余、虚拟机数量与状态、Agent 与 libvirt 健康、任务积压/失败/耗时。**每个采样值带时间戳；采集失败返回未知，禁止用 0 伪装**。
- **对账**：数据库实例 ↔ libvirt 域；磁盘记录 ↔ 实际文件；任务状态 ↔ 资源实际状态；预留 ↔ 实际占用。流程 = 检测 → 差异记录 → 安全修复 → 有破坏风险的转人工。
- **告警**：节点离线、Agent 认证失败激增、资源不足、任务长时间未结束、磁盘空间低、libvirt 不可用、孤儿域/孤儿磁盘。MVP 先在仪表盘展示，通知渠道作为后续模块。
- **验收**：对账能发现注入的孤儿域/孤儿磁盘；告警在仪表盘可见；采集字段缺失时不误报 0。
- **回滚**：对账默认只读，关闭修复开关即可回退。

### 模块 O：安全加固（NEW / 阶段 4）

- **目标**：落实《手册》17.1 全部必须项并通过威胁测试。
- **文件改动**：跨模块配置与代码加固（Token/TLS、密钥注入、HTTPS 与安全 Cookie、CSRF/CORS/ALLOWED_HOSTS、DEBUG 关闭、PostgreSQL 最小权限与不对外、Agent 白名单、路径校验、危险操作授权审计、上传限制、依赖锁定与补丁、限流与高风险操作额外验证）+ 加固检查清单脚本。
- **威胁测试**：伪造 Agent Token；路径穿越；镜像名/域名/XML 字段注入特殊字符；越权访问他人对象；重放删除请求；并发创建导致超分；通过错误信息探测路径或凭据；直连 Agent 管理端口。
- **判定**：任何可造成未授权命令执行、任意文件访问或磁盘误删的问题，均为**阻断发布级缺陷**。
- **验收**：威胁测试逐项通过并留证；生产部署验证 DEBUG 关闭、Agent 不暴露公网、Token 强度与轮换说明齐备。
- **回滚**：配置项可回退；Token 轮换需先双 Token 兼容再撤旧。

### 模块 P：备份、恢复与升级（NEW / 阶段 6）

- **目标**：数据库与配置可恢复，升级可回滚，版本与迁移可追溯。
- **文件改动**：备份脚本与定时任务、恢复演练记录模板、版本与迁移记录表、升级/回滚 runbook、前端备份能力真实化（未实现前不得显示“备份成功”）。
- **数据库备份**：官方或已验证工具；备份落独立于系统盘的受控位置；定义保留周期、加密与访问权限；**必须做恢复演练，仅有备份文件不算完成**。
- **虚拟机备份**：明确关机备份或一致性快照、是否含磁盘/配置/EFI-NVRAM/元数据、目标与容量、失败重试与校验、恢复到原节点或新节点、恢复后网络/UUID 冲突处理。
- **升级回滚**：记录应用版本、迁移版本、Agent 版本；升级前备份；迁移考虑向前兼容，不可逆迁移须有恢复计划；Agent 与后端 API 版本兼容性检测；升级失败可回滚应用；数据库回滚策略单独说明（不得假设 migrate 总能安全逆转）。
- **验收**：完成一次恢复演练并出记录；升级/回滚 runbook 可执行；前端未实现的能力不显示成功状态。
- **回滚**：按 runbook 回退版本与迁移；保留备份集。

## 4. 统一完成定义（DoD，逐卡勾选）

- [ ] 功能代码存在，异常分支已实现（非空实现、不吞异常）
- [ ] 参数校验、权限检查、日志记录完整（含 request_id / task_id / node_id / instance_id）
- [ ] 自动化测试通过（本卡要求层级全部执行，附真实输出）
- [ ] 格式检查、静态检查或构建通过（Python/Go/TS 各自门禁）
- [ ] API / 配置 / 数据库变更已更新文档（ARCHITECTURE.md、ENVIRONMENT_DEPLOYMENT.md）
- [ ] 无密钥、Token、密码入库；密钥扫描通过
- [ ] 无未解释的 TODO、空实现、吞异常代码
- [ ] 无法在本环境验证的项目明确标记 NOT VERIFIED / BLOCKED，**不得声称通过**
- [ ] 状态表与路线图已回填

## 5. 完成后输出模板（每张卡必交）

```text
模块 / 任务卡：
提交版本（Commit）：
状态：EXISTS-KEEP / EXISTS-FIX / NEW→DONE / BLOCKED
变更文件清单（文件 → 作用）：
数据库迁移：
API 请求/响应样例：
配置项及默认值：
测试命令与实际结果（含退出码）：
手工验证步骤：
已知限制 / NOT VERIFIED 项：
回滚方式：
兼容性影响与下一任务建议：
```

## 6. 任务卡领取模板（首次进入某模块时填写）

```text
任务 ID / 名称：
目标：
当前实现检查：已存在文件 / 缺失文件 / 相关调用方 / 相关模型
实现范围 / 不在本次范围：
具体文件改动：
接口与数据结构：
业务流程：
异常场景：
权限与安全要求：
测试用例：
执行命令：
验收标准：
回滚方式：
```
