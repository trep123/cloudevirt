# 持久共享工作台

> 当前顶栏默认采用[直接页面共享](PAGE_SHARING.md)，操作正常平台页面即可推流。以下为保留的服务端持久工作台方案，普通页面共享无需此窗口或浏览器服务组件。

用户从顶栏进入“共享工作台”，开启独立的服务端浏览器，再点击“进入工作台”操作平台。观看者通过分享链接只读观看这个浏览器内的整个页面，包含列表、详情和打开的虚拟机控制台。普通本地标签页的导航不会同步到工作台；操作应在工作台内进行。

断开本地控制、关闭本地标签页或退出本地账号，不会结束服务端浏览器。主动停止、到期、账号禁用、权限撤销、强制改密、密码变更或工作台内部退出登录会结束工作台。账号变更由后台任务检查，默认间隔 15 秒。

## 安装

在完整的新版本源码目录执行（Ubuntu 26 amd64）：

```bash
sudo bash install.sh --source "$PWD" --domain 192.168.100.100 --enable-workbench
```

此选项同时安装现有媒体通道。安装程序会迁移数据库、同步角色权限、安装浏览器组件并创建后台任务。升级会重启平台服务，应安排维护时间。已有数据库与虚拟机磁盘沿用原配置。

浏览器运行时使用固定版本 `playwright-core` 及配套 Chromium，安装在管理应用之外，以便独立服务无法读取管理应用与节点凭据。自签名 HTTPS 证书导入每个工作台私有 NSS 数据库。使用自有 CA 时，单独安装组件可指定：

```bash
sudo bash scripts/install_workbench.sh --origin https://cloudvirt.example --ca /path/to/platform-ca.crt
```

单独安装组件之后仍需完成应用升级、数据库迁移、`sync_roles`、启用 `WORKBENCH_ENABLED=true`、安装并启用 `cloudvirt-reconcile_workspaces.timer`。完整安装器负责这些步骤。

默认管理端配置：

```dotenv
WORKBENCH_ENABLED=true
WORKBENCH_AGENT_ENDPOINT=http://127.0.0.1:9100
WORKBENCH_MAX_SESSIONS=2
```

`/etc/cloudvirt/workbench.json` 为 root 专用配置，固定平台 origin、浏览器和运行时路径；`limit` 是节点实际并发上限。增加并发时同时调整管理端上限和节点 `limit`，并确认内存、CPU、编码能力。每个浏览器默认内存上限 1536 MB、CPU 上限 150%，最多运行 24 小时。媒体编码仍受原有桌面发布器并发限制。

使用现有 MediaMTX 完成一对多转发，首版不迁移到 SRS。媒体信令保持本机，由平台鉴权后代理；公网和跨网段观看需另外配置 ICE/TURN 与防火墙。默认仅面向安装时配置的局域网。

## 后端接口

| 接口 | 用途 |
| --- | --- |
| `GET /api/v1/console/workspaces/my` | 本人工作台及串流状态 |
| `POST /api/v1/console/workspaces/my` | 幂等开启；`expires_hours` 为 1–24，重复请求不重新生成链接 |
| `DELETE /api/v1/console/workspaces/my` | 异步停止，立即撤销凭证 |
| `POST /api/v1/console/workspaces/my/link` | 轮换只读分享链接，旧链接与旧观看租约失效 |
| `POST /api/v1/console/workspaces/{id}/sessions` | 本人控制票据 |
| `POST/DELETE /api/v1/console/workspace-sessions/{id}` | 续租/释放本地控制连接 |
| `POST /api/v1/console/workspaces/{id}/bootstrap` | 服务器浏览器一次性登录，仅接收短期专用凭证 |

观看者复用 `/console/broadcasts/{id}/watch` 和 `/console/watch-sessions/{id}`。当前授权方式为匿名能力链接；持有完整链接的人能够观看。策略接口保留在 `broadcast_access.py`，后续可以增加登录授权或邀请制。观看凭证不授予任何用户或虚拟机 API 权限。

## 隔离和生命周期

- `console.use_workspace` 为独立权限，默认同步给 Admin、Operator、Viewer；资源访问仍由原有对象权限决定。
- 每个用户最多一个工作台。服务端浏览器使用独立 DynamicUser、0700 私有目录、私有 X11 凭据、随机 VNC 密码、启用沙箱的 Chromium；没有宿主机 libvirt socket、应用凭据或管理目录访问权。
- 浏览器仅导航平台同源页面；弹出页关闭，HTTP 和 WebSocket 请求限制到平台 origin。暂不支持工作台内上传本地文件或下载文件；用户应从普通平台页面上传。
- Node Agent 保留 `NoNewPrivileges` 和只读文件系统隔离。独立 root 启动代理仅通过 `/run/cloudvirt-workbench/control.sock` 接收 UUID 范围内的 start/status/stop，校验 Unix peer UID；不提供任意命令或任意路径执行接口。
- 服务端通过 120 秒一次性启动凭证建立新的 Django 登录会话；不复制本地会话 Cookie，也不保存用户登录密码。确认用户身份及工作台标记后才开始采集。凭证不进入命令参数、查询字符串或访问日志。
- 本地控制使用一次性签名票据，并绑定用户、登录会话、工作台和 generation。重建后的工作台不接受旧票据。只读观看走独立媒体通道。
- 链接令牌只保存哈希，放在 URL fragment。API 不返回历史明文链接；遗失链接时轮换。停止时撤销专用浏览器登录、观看授权和控制票据，再由后台任务停止编码进程和 systemd 单元。

## 运行检查

```bash
systemctl status cloudvirt-workbench-broker.service cloudvirt-reconcile_workspaces.timer
journalctl -u cloudvirt-workbench-broker -u cloudvirt-reconcile_workspaces -u cloudvirt-reconcile_broadcasts -n 80
systemctl list-units 'cloudvirt-workbench-*'
```

`READY` 表示浏览器完成登录；`LIVE` 表示媒体服务实际检测到发布。两者独立显示。启动失败不会伪装成可观看。UI 轮询降频并标记过期状态。Worker 中断时，采集进程的现有租约会到期退出，浏览器单元另有 `RuntimeMaxSec` 到期限制。

## 验证记录

2026-10-28 在 Ubuntu 26.04.1 / kernel 7 的独立临时环境验证，未登录生产管理员账号、未操作现有虚拟机：

- PostgreSQL 独立测试库中控制台测试 28 项通过，包含 9 项新工作台权限、一次性启动、会话隔离、密码变更、到期和停止测试。
- Go Node Agent 全部测试通过；新增票据混合作用域和缺失 generation 拒绝检查。
- TypeScript 类型检查、Vite 生产构建通过；前端 17 项测试覆盖路由权限、匿名接口、连接恢复与资源释放。
- 启用 Chromium 沙箱和 HTTPS 证书校验，实际启动服务端浏览器并完成平台登录。
- 非 root Agent 在原有服务隔离下，通过 Unix broker 启动工作台；Nginx 鉴权、票据、VNC 握手完整通过。
- 两个无平台 Cookie 的浏览器观看端同时播放同一工作台 WebRTC 画面，实际视频 1280×720；另行解码 8 帧 H.264 视频。
- 关闭本地控制连接后继续运行；主动停止后专用 Django 会话删除，浏览器单元及私有目录回收。

浏览器与 AppArmor 适配依据：[Playwright 浏览器管理](https://playwright.dev/docs/browsers)、[Chromium 的 Ubuntu user namespace 说明](https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md)。
