# CloudVirt 编码规范

- 版本：1.0（草案）　日期：2026-10-26
- 定位：把仓库内 `rule_py.md`、`rule_cpp.md` 落到本项目，并补齐 Go / TypeScript 的最小约定。

## 1. 规范来源与适用范围

| 语言 / 区域 | 适用规范 | 说明 |
| --- | --- | --- |
| Python（Django 后端、脚本） | `rule_py.md` **全部条款** | 强制项即 CI 拦截项 |
| C / C++ | `rule_cpp.md` **全部条款** | 本项目当前无 C/C++ 代码；一旦引入（性能扩展、系统工具）即生效 |
| Go（节点 Agent） | `rule_go` 缺失 → 本文第 3 章最小集 + `gofmt`/`go vet` | 建议后续补充独立 Go 规范文件 |
| TypeScript / React（前端） | 本文第 4 章最小集 | 建议后续补充独立前端规范文件 |
| 提交 / 分支 | 本文第 5 章 | 两规范文件的 Git 章节一致，统一执行 |

## 2. 项目级统一约定（跨语言）

### 2.1 文件头与注释

- Python 文件必须有文件头注释（`rule_py.md` 12 章模板）与模块 docstring；公共函数必须写 Google 风格 docstring。
- Go 每个包必须有包注释，`cmd` 入口文件说明用途与配置来源；导出标识符必须有注释。
- TypeScript 模块导出必须有 JSDoc 或 TSDoc 注释说明用途；公共 API 类型必须注释。
- **注释语言：中文**；专有名词、标识符、错误码保留原文（如 `qemu-img`、`LIBVIRT_UNAVAILABLE`）。

### 2.2 日志

- 后端使用 `logging`（禁 `print`）；Agent 使用结构化日志（推荐 JSON，字段见 ARCHITECTURE.md 第 7 章）；前端不得打业务日志到控制台（生产构建禁用 `console.*`）。
- 必须使用占位符延迟格式化，禁止 f-string / 字符串拼接 / 外部输入作为格式串。
- 异常日志必须带上下文：`logger.exception("创建域失败: instance_id=%s", instance_id)`。
- 禁止记录：Token、密码、私钥、cloud-init 口令、完整数据库连接串、Authorization 头。

### 2.3 错误处理与错误码

- 后端：自定义异常继承项目基础异常 `AppError`，业务异常携带 `code`（见 ARCHITECTURE.md 5.4）；DRF 统一异常处理器转换为统一错误结构。
- Agent：错误码常量集中定义，HTTP 状态映射集中在一个模块，禁止散落 `http.Error` 硬编码。
- 前端：`src/api/` 统一解析错误码，禁止各组件自行判断；不得把原始堆栈展示给用户。
- 禁止吞异常；捕获后必须处理、记录或重新抛出（`raise ... from e` / `fmt.Errorf("...: %w", err)`）。

### 2.4 命名与 API 契约

- JSON 字段统一 `snake_case`；时间统一 ISO 8601 UTC；枚举使用大写字符串（如 `RUNNING`、`OFFLINE`）。
- URL 使用复数资源集合（`/instances/`、`/nodes/`），操作子路由使用动词（`.../start/`）。
- 数据库表名沿用 Django 默认；字段命名 `snake_case`；布尔字段 `is_` 前缀。

### 2.5 配置与安全

- 配置与代码分离，禁止硬编码地址、端口、路径、超时；敏感配置一律环境变量注入。
- 禁止提交 `.env`；`.env.example` 只允许占位值。
- 外部命令一律使用参数数组（Python `subprocess.run([...], shell=False)`；Go `exec.CommandContext`），禁止拼接 shell 字符串。
- 文件路径必须规范化并校验位于允许根目录内；上传必须校验类型、大小、并发与超时。

### 2.6 数据库与迁移

- 每次模型变更必须生成迁移并在 CI 执行 `makemigrations --check --dry-run`。
- 禁止在循环内逐条查询（N+1）；列表查询显式字段，禁用 `SELECT *` 等价写法。
- 事务边界明确：禁止在数据库事务内等待外部 HTTP（Agent 调用必须在事务提交后）。
- 不可逆迁移必须在文档写明恢复计划。

### 2.7 测试

- 新代码必须有单元测试，核心逻辑行覆盖率 ≥ 80%。
- 测试独立、可重复、无外部依赖（AIR）；禁止固定 `sleep`；临时文件使用 `tmp_path` / `t.TempDir()`。
- 命名：Python `test_*.py` / `test_*`；Go `*_test.go`（用例名 UpperCamelCase）；TS `*.test.ts`。
- **禁止只用 mock 完成全部验收**：涉及 libvirt/KVM 的验收必须在真实宿主机执行（`TEST_ACCEPTANCE_PLAN.md`）。

## 3. Go 最小约定（节点 Agent）

1. 格式与静态检查：`gofmt -l .` 必须为空，`go vet ./...` 零告警。
2. 包名小写单数、无下划线；目录与包名一致。
3. 导出标识符加注释；错误统一 `fmt.Errorf("上下文: %w", err)` 包装，禁止丢弃错误（禁止 `_ =` 忽略错误，除非显式说明）。
4. 所有外部命令使用 `exec.CommandContext` + 参数数组 + 超时；禁止 `exec.Command` 拼接用户输入。
5. 并发：共享可变状态必须加锁或使用 `sync/atomic`；HTTP handler 不得持有全局可变状态；禁止在 handler 内启动无管控 goroutine（需有明确生命周期与 WaitGroup/context）。
6. 配置启动时一次性加载并校验，缺失或非法立即退出并给出明确错误（对齐 `rule_cpp.md` 18 章思路）。
7. 表驱动测试为主，覆盖：参数校验、错误映射、路径校验、超时。

## 4. TypeScript / React 最小约定（前端）

1. 严格模式：`strict: true`；禁止 `any` 作为 API 默认类型，确需使用必须写原因注释。
2. 所有请求集中在 `src/api/`；组件不得自拼 URL、不得自行实现错误解析。
3. 组件函数化 + hooks；状态不得只用颜色表达（需文字或图标）。
4. 轮询任务必须在组件卸载时清理（`useEffect` 返回清理函数）。
5. 表单即时校验仅作提示，最终校验以服务端为准。
6. 构建前 `npm run lint`、`npm run typecheck`、`npm run build` 必须通过；提交锁文件后使用 `npm ci`。

## 5. 提交与分支

- 提交信息使用 Conventional Commits：`feat:`、`fix:`、`docs:`、`refactor:`、`test:`、`perf:`、`build:`、`ci:`、`chore:`；scope 建议为模块名（如 `feat(instances): ...`）。
- 一个提交只做一件事；禁止提交密钥、真实配置、大文件与构建产物。
- 分支命名：`feature/xxx`、`bugfix/xxx`、`hotfix/xxx`；主分支保护，合并需评审与 CI 通过。
- 提交前必须通过 pre-commit：格式化检查、静态检查、密钥扫描（gitleaks / detect-secrets）。

## 6. CI 门禁矩阵

| 组件 | 格式 | 静态/类型 | 测试 | 构建 | 其他 |
| --- | --- | --- | --- | --- | --- |
| 后端（Python） | ruff format --check | ruff check、（可选 mypy） | `python manage.py test` | `python manage.py check` | `makemigrations --check --dry-run`、gitleaks |
| Agent（Go） | gofmt -l | go vet | `go test ./...` | `go build ./...` | gitleaks |
| 前端（TS） | prettier（或 eslint --fix 检查） | eslint + tsc --noEmit | vitest / jest | `npm run build` | 锁文件存在性检查、gitleaks |
| 文档 / 配置 | — | — | — | — | `.env` 未入库检查、密钥扫描 |

- 任一门禁失败即不得合入；本地未跑通的构建不得在验收记录中记为通过。

## 7. 与规则文件的偏差登记

| 偏差 | 原因 | 处理方式 |
| --- | --- | --- |
| 缺少 Go / 前端规则文件 | 仓库仅提供 `rule_py.md`、`rule_cpp.md` | 本文档第 3、4 章定义最小集，后续补充独立规范文件 |
| Python 版本 3.14 下依赖版本未定 | 尚未实测安装 | 标 TBD(待实测回填)，禁止凭空锁定版本 |
