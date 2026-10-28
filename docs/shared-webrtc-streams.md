# 服务端串流发布与匿名观看

本版将原工作区的 WebRTC 本地播放改为「开启串流 → 生成观看链接 → 其他用户观看」。
支持虚拟机桌面和已登记的独立视频源。发布端不创建 WebRTC 接收连接或视频元素；
noVNC 仍用于原有的桌面操作，两条链路互不授予额外权限。

## 使用流程

1. 在虚拟机详情打开「桌面与视频」工作区。
2. 选择链接有效期（1–24 小时，默认 12 小时）。
3. 点击「开启桌面串流」，或选择独立视频源后点击「开启视频源串流」。
4. 复制观看链接给其他人。观看页不需要平台账号，只提供视频观看、声音和全屏。
5. 发布者离开页面后，服务端继续推流。点击「停止串流」、链接到期或资源授权失效后结束。
6. 「重新生成链接并撤销旧链接」不重启桌面采集，但会撤销旧链接和旧观看会话。

链接凭证仅在生成响应中返回一次，不以明文存入数据库。发布页刷新后需重新生成才能再次分享。
重新生成后，先前已经观看的用户也需要新链接。分享链接属于观看凭证，应只发给预期的观看者。

## 两种发布链路

| 类型 | 数据路径 | 开启后的实际行为 |
| --- | --- | --- |
| 桌面 | 节点本地 VNC → GStreamer RFB 只读采集 → H.264 → MediaMTX → 观看端 WebRTC | Agent 在后台启动采集进程，不依赖发布者的浏览器 |
| 独立视频源 | 已配置的发布/拉流路径 → MediaMTX → 观看端 WebRTC | 开放此路径的观看授权；已有发布进程继续工作，按需拉流由观看请求触发 |

独立视频源仍需先在服务器发布或配置可信的拉流地址；登记一个名称不会凭空创建视频。
前端不接受任意上游 URL，不返回摄像机、RTSP 发布或 VNC 认证凭据。

桌面使用完整帧快照，采集限速 15 Hz，输出 1280×720、15 FPS、基线 H.264，
目标码率 2500 kb/s，保留宽高比。完整快照避免增量 RFB 缓冲经过连续编码后丢失静态像素。
这是软件编码的起点配置，尚未承诺高运动画面的质量、CPU 占用或并发性能。
桌面音频不通过 RFB 提供；独立源的音频取决于实际编码与浏览器支持。

## 权限与接口扩展点

当前只实现 link 授权模式：持链接者可以匿名观看。
已保留 Broadcast.access_mode 和 ViewerPolicy 接口，授权判断集中在 broadcast_access.py。
未来可增加指定用户或登录用户策略，同时提供对应的身份认证适配与前端凭证模式；
这两种模式尚未启用。

观看授权与虚拟机管理授权独立。匿名观看者不能使用虚拟机、节点、noVNC 控制或用户管理 API。
发布管理继续使用平台登录、CSRF 和资源所有权校验，管理员按现有权限管理资源。

- 链接凭证为 256 位随机数，放在 URL fragment 中，HTTP 请求 URL 不携带凭证。
  观看请求通过 X-Stream-Token 头提交，数据库只保存 SHA-256 摘要。
- 每个观看会话另有独立随机凭证，通过 X-Media-Session-Token 续租和关闭。
  知道分享链接也不能操作其他观看者的会话。
- 匿名观看请求不携带平台 Cookie、不发送平台 CSRF 凭证、不触发登录跳转。
- 观看会话租约 90 秒，客户端每 20 秒续租；默认每路最多 16 个活跃/待连接观看会话。
- 过期、停流、禁用源和链接版本变更都会阻止新观看及续租，并进入服务端回收流程。
  媒体网关管理接口故障时，不能保证已有 SRTP 会话在固定时间内被强制关闭。
- 发布、停止、链接轮换和观看会话建立会记录审计事件；凭证和完整 SDP 不写入审计。

## API 契约

统一前缀 /api/v1，观看与管理端均通过 HTTPS。

| API | 认证 | 含义 |
| --- | --- | --- |
| GET /console/instances/{id}/broadcasts | 平台 Session + 资源范围 | 查询发布状态 |
| POST /console/instances/{id}/broadcasts | Session + CSRF + 资源范围 | 开启桌面/源串流，返回 202 |
| POST /console/broadcasts/{id} | Session + CSRF + 资源范围 | 轮换观看链接及有效期 |
| DELETE /console/broadcasts/{id} | Session + CSRF + 资源范围 | 请求停止，返回 202 |
| GET /console/broadcasts/{id}/watch | X-Stream-Token | 观看元数据、ICE 配置与是否可连接 |
| POST /console/broadcasts/{id}/watch | X-Stream-Token | 提交 JSON SDP，建立观看会话 |
| POST /console/watch-sessions/{id} | X-Media-Session-Token | 续租本观看会话 |
| DELETE /console/watch-sessions/{id} | X-Media-Session-Token | 关闭本观看会话 |

开启请求示例：

```json
{"kind":"desktop","expires_hours":12}
```

独立源使用 {"kind":"source","source_id":实际源ID,"expires_hours":12}。
返回的 watch_path 为 /watch#广播UUID.随机凭证；ID 和凭证均由服务端生成。
观看会话响应包含 session_id、SDP answer 和 lease_token，不包含上游会话地址。

状态为 QUEUED、STARTING、LIVE、WAITING、STOPPING、STOPPED、ERROR。
LIVE 来自真实媒体网关路径的 ready 状态，不根据按钮点击推断成功。
独立源可在 WAITING 时发起 WHEP 请求，以支持按需拉流；没有实际帧不会显示正在观看。

## 后台进程与部署

根目录安装器更新全部组件并安装媒体依赖：

```bash
sudo bash install.sh --source /opt/cloudevirt/cloudevirt --domain 192.168.100.100 --enable-media
```

该命令会更新在线应用并重启相关服务，应在维护窗口执行。本次开发只更新仓库并进行隔离验证，
没有执行在线升级。

新增组件：

- Agent 的桌面发布管理器与 scripts/publish_desktop.py。
- GStreamer rfbsrc、imagefreeze、x264enc、rtspclientsink 和 Python GI。
- console.0002_shared_broadcasts 数据库迁移。
- cloudvirt-reconcile_broadcasts.service/.timer，每 15 秒协调状态和续租。
- 现有 cleanup_console_sessions 回收过期或已撤权的观看会话。

桌面发布进程的凭据经 stdin 传入，不出现在进程命令行。
Agent 采用约 90 秒的进程租约，管理服务失联后自动终止采集。
每节点默认最多 2 路桌面采集，每用户默认最多同时开启 3 路串流。
发布状态由后台任务维护，发布者页面不负责续租。

| 配置 | 默认 |
| --- | --- |
| 管理服务 MEDIA_API_BASE_URL | http://127.0.0.1:9997 |
| 管理服务 BROADCAST_MAX_VIEWERS | 16 |
| Agent CLOUDVIRT_MEDIA_PUBLISH_BASE_URL | rtsp://127.0.0.1:8554 |
| Agent CLOUDVIRT_DESKTOP_PUBLISHER_SCRIPT | /opt/cloudvirt/services/virt-node-agent/scripts/publish_desktop.py |
| Agent CLOUDVIRT_DESKTOP_STREAM_LIMIT | 2，支持 1–8 |

默认媒体信令、管理和 RTSP 仅监听本机，ICE 使用原有受限 UDP 8189。
跨节点发布需运维配置受保护的中心媒体发布地址、认证、路由和防火墙；
本版不自动开放公网 RTSP、部署 TURN 或配置跨节点信任。
独立安装媒体组件不会自动替换旧 Agent，升级时必须同步更新管理服务、Agent 和前端。

## 验证记录（2026-10-28）

Ubuntu 26.04.1、独立 PostgreSQL 数据库与测试端口、临时无磁盘 KVM 虚拟机。
Chrome 隔离浏览器上下文验证，未操作已有虚拟机。

- 发布端 video 元素为 0，RTCPeerConnection 创建次数为 0。
- 两个匿名浏览器上下文并发收到真实 1280×720 桌面流，含 BIOS 文字像素检查，
  避免将有尺寸的黑帧误判为画面正常。
- 发布者离开页面后观看持续；链接轮换撤销既有观看，重新生成的链接可用。
- 已在发布者离开后连续观看 95 秒，跨过 90 秒租约窗口；真实文字像素仍在，验证后台续租生效。
- 停止串流后观看被撤销；独立测试源收到真实 640×360 视频。
- 匿名观看上下文无平台 Cookie，直接请求虚拟机 API 为 401。
- 74 项相关后端测试、16 项前端测试、类型检查、生产构建与 Go 竞态测试通过。
- 进程限额、幂等启动、撤销、控制端失联后的租约过期有真实子进程测试。

尚未完成真实摄像机、跨公网、跨节点、移动端/Safari、长时间运行及性能容量验收。
全量后端的既有失败延续首版记录，见 console-media-workspace.md；不能视为本版全部通过。

组件资料：[rfbsrc](https://gstreamer.freedesktop.org/documentation/rfbsrc/index.html)、
[imagefreeze](https://gstreamer.freedesktop.org/documentation/imagefreeze/index.html)、
[rtspclientsink](https://gstreamer.freedesktop.org/documentation/rtspclientsink/index.html)。
