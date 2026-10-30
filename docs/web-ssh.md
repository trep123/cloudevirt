# Web SSH

## 页面位置与用途

- 虚拟机详情页顶部“Web SSH”按钮，与 noVNC 图形控制台并列；虚拟机列表“更多 → Web SSH”。不新增独立主导航，避免脱离资源上下文。
- 独立路由 `/admin/vms/{id}/ssh`、`/app/vms/{id}/ssh`，显示虚拟机名称、返回入口、连接状态与终端。普通用户只能进入本人授权资源。
- 用客体 OS 的 SSH 账号执行命令、编辑配置；平台角色不等于客体 root，不自动安装 sshd、不自动提权。
- noVNC 用于安装系统、图形操作和网络故障救援；SSH 用于日常命令行配置。

## 首版能力与边界

支持密码及 PEM/OpenSSH 私钥（可带口令）、UTF-8 交互式 PTY、终端自适应、页面/浏览器全屏、主动断开。使用固定端口 22。虚拟机需运行、状态未过期且节点可用，客体已启用 SSH 服务并允许对应认证方式；Windows 客体需安装并启用 OpenSSH Server。

目标地址仅接受节点确认的 MAC 绑定 DHCP 租约：libvirt lease 来源，以及 OVS 专用租约文件中未过期的地址。不信任 Guest Agent/ARP 自报地址，不允许任意主机名、端口、手工静态 IP、loopback/link-local 或节点自身地址。静态地址、外部桥接 DHCP 暂无可信记录时，入口会显示说明；可先通过 noVNC 配置，未来增加管理员审批的固定目标绑定。

首次连接每次都显示真实 SSH 主机公钥 SHA-256 指纹，必须通过可信渠道核对并确认；未确认或指纹不符，不向 SSH 服务提交登录认证。信任仅限本次连接，不使用 InsecureIgnoreHostKey、不自动记住或覆盖指纹。

## 会话与安全

- 新权限 `instances.ssh_instance`，内置管理员、Operator、Viewer 可使用；自定义角色可独立分配，依赖 instances.view_instance。后端同时校验本人归属、用户/角色节点范围与节点授权。
- REST 只接收 address，禁止接收 SSH 密码/私钥。凭据从浏览器经同源 WSS、nginx 内部授权、Agent 传递，在内存中用于 SSH 握手，不入数据库/URL/日志/浏览器持久存储。Node Agent 为可信代理，会在内存中处理凭据。
- 复用 ConsoleSession 的登录绑定、单次票据、90 秒租约、25 秒续期、注销/撤权检查、并发会话上限。SSH 与 VNC 共享上限，但票据协议隔离，不能交叉使用。
- nginx 继续使用现有 /console-ws/ 内部 auth_request，不向浏览器暴露 Agent 共享 token，无新增公网端口；默认要求 HTTPS；远程 Agent 也必须使用可信 HTTPS，仅同机 loopback Agent 允许 HTTP，以免节点间明文传输凭据。
- Agent 在拨号前再次核对域运行状态与地址租约，固定 IP 字面量与 22 端口，不提供通用跳板、TCP 转发、SFTP、文件管理或任意宿主机 shell。
- 认证阶段最多 60 秒，会话最长 2 小时；断开/关闭页面释放连接，未续租则过期关闭。不自动重连或重放认证，不记录终端命令内容。会话创建、网关授权和显式关闭使用现有审计链路。
- 无法可靠在线“擦除”运行时字符串的所有内存副本；上述“不保存”指不持久化，部署应信任管理端与 Agent 主机。

## 接口

- GET `/api/v1/console/instances/{id}/ssh`：授权地址列表及端口。
- POST 同路径，body={"address":"节点确认的地址"}：创建一次性会话，返回 session_id、同源 path 和 lease_seconds，不返回内部签名票据。
- POST/DELETE `/api/v1/console/sessions/{session_id}`：续期/关闭。
- Agent 内部 GET `/api/v1/domains/{name}/ssh-targets`：受 token 保护的目标查询。
- Agent /ssh：仅接受内部签名的 SSH 票据及同源 WebSocket；WebSocket 消息 auth → hostkey → trust → ready，之后 input/resize 与二进制输出。

## 部署与验收

标准安装器执行迁移和 sync_roles 后生效，nginx console-gateway 配置无需新增位置；需要更新所有要支持 SSH 的节点 Agent。

测试使用隔离 PostgreSQL 与临时本地 SSH 协议服务，覆盖 PTY、输入/输出、缩放、指纹确认前不认证、错误指纹拒绝、退出清理、地址租约归属、过期租约、对象权限、HTTP 拒绝和 VNC 兼容。没有为验收而启动用户虚拟机、修改客体配置或使用用户真实客体凭据。真实客体登录需由用户在运行且具备可信租约的虚拟机上完成。
