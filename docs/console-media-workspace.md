# 桌面与独立视频工作区（第一版）

## 已实现范围

在现有虚拟机详情页点击「桌面与视频」或运行中虚拟机的「控制台」。
同一工作区提供 noVNC 桌面、独立 WebRTC 视频、分屏/上下布局、质量配置、手动剪贴板、
键鼠捕获与释放、全屏、接收端实测统计。虚拟机关闭时仍可观看独立视频。

桌面继续使用 QEMU/libvirt VNC + noVNC 1.7.0；不修改 noVNC 核心、不改 RFB 编码协议。
独立视频使用 MediaMTX v1.21.3 WHEP（服务端代理 SDP）和浏览器原生 WebRTC。
本版没有把虚拟机桌面自动转换成 WebRTC 视频，也没有实现视频录制、摄像机自动发现、
GPU 编码或跨公网 TURN 服务部署。

## 四条链路

| 链路 | 路径 | 边界 |
| --- | --- | --- |
| 授权 | 浏览器 Session + CSRF → DRF 对象权限 → 数据库短期会话 | 普通用户仅能访问自己的虚拟机及绑定视频源 |
| 桌面 | 浏览器 WSS → Nginx auth_request → 该虚拟机所属节点 Agent → 127.0.0.1 VNC | 节点由服务端已登记 endpoint 决定 |
| 视频信令 | 浏览器 SDP → DRF → 本机 MediaMTX WHEP | 真实上游会话 URL、发布凭据不返回浏览器 |
| 视频媒体 | 浏览器 ↔ MediaMTX ICE/DTLS/SRTP | 与桌面的连接、故障恢复、资源释放独立 |

桌面 URL 只有随机会话 ID，不含 Agent 令牌、域名签名或 VNC 密码。
Nginx 内部认证子请求需要服务端派生密钥；公共认证地址返回 404。
Agent 只接受内部头中的 HMAC 一次性票据，拒绝旧的查询字符串授权。
VNC 密码因 RFB 认证需要，只随已授权的 POST 响应进入客户端内存；不得写入 URL、
日志、浏览器存储。主机管理凭据和共享 Agent 令牌不会返回前端。

## 会话与权限

- 建立桌面授权有效期 30 秒、单次领取；数据库行锁防止重复领取。
- 活跃桌面租约 90 秒，浏览器每 20 秒通过 CSRF 保护的 POST 续租。
  Agent 同时设置浏览器连接与 VNC 连接的硬截止时间，过期无需依赖浏览器合作。
- 每用户最多 3 个桌面会话及 3 个视频会话；每 Agent 最多 64 个已保留/活跃桌面连接。
- 视频租约为 90 秒，每 20 秒续租；30 秒一次的 cleanup_console_sessions 关闭过期会话。
  正常停止或卸载工作区立即请求释放。视频撤权依赖媒体网关管理接口可达；
  该接口故障时不能承诺现有 SRTP 会话在固定时间内被强制断开。
- 登出标记当前登录身份的会话过期；后续请求仍执行 Session、角色与对象级校验。
- 网络错误使用 2/4/8 秒的有限重连；401/403/404/409 停止自动重试。
  连接稳定 30 秒后才重置重试预算，避免反复短连接无限重试。
- 桌面在页面隐藏 30 秒后暂停；恢复时重新授权。窗口失焦释放按键。
  视频保持独立播放，关闭工作区或离开页面时释放 peer、track、定时器与会话。
- 本地只读模式只是输入选项，不是新的安全权限；观看控制台仍要求资源访问权限。
- TURN REST 凭据按用户临时生成，每次视频连接重新获取 ICE 配置，服务器密钥不返回前端。
- 旧 GET /api/v1/instances/{id}/console 已返回 410；客户端需使用新 POST 接口。

## 部署

需要整体更新 Django、Agent、前端和 Nginx，不能仅替换前端。
新安装或更新部署可使用仓库根目录安装器（会重启应用服务，应选择维护窗口）：

```bash
sudo bash install.sh --source /opt/cloudevirt/cloudevirt --domain 192.168.100.100 --enable-media
```

安装器默认 HTTPS。使用域名时需另设实际可达 IPv4：

```bash
sudo CLOUDVIRT_MEDIA_HOST=192.168.100.100 bash install.sh --source /opt/cloudevirt/cloudevirt --domain virt.example.com --enable-media
```

安装器会应用迁移、生成仅供 Nginx 内部使用的认证片段，并开启清理定时器。
媒体网关为可选组件，下载固定版本并验证官方 SHA-256 清单。
现有 /etc/cloudvirt/mediamtx.yml 会保留，升级时需要核对新增配置。
独立安装媒体网关也可运行 sudo bash scripts/install_media.sh --host 192.168.100.100。

默认端口：

| 服务 | 监听 |
| --- | --- |
| HTTPS | 443 |
| Django / Agent | 127.0.0.1:8000 / 127.0.0.1:9100 |
| 媒体 WHEP / API / RTSP | 127.0.0.1:8889 / 127.0.0.1:9997 / 127.0.0.1:8554 |
| WebRTC ICE | UDP 8189，广告地址为配置的 IPv4 |

RTMP、HLS、SRT、MoQ、回放、性能调试入口显式关闭。
只允许本机读取/发布媒体与调用管理 API。UFW 已启用时，脚本默认允许该 IPv4 所在
/24 网段访问 UDP 8189；可用 CLOUDVIRT_MEDIA_ALLOWED_CIDR 指定真实客户端网段。
跨子网/NAT 需单独规划路由、端口与 TURN；本版不自动部署公网中继。
脚本不会修改宿主机默认路由或已有 OVS 配置。

管理服务环境项（/etc/cloudvirt/management.env）：

| 变量 | 默认 / 用途 |
| --- | --- |
| CONSOLE_REQUIRE_TLS | 非 DEBUG 默认开启；HTTP 下拒绝新会话 |
| CONSOLE_MAX_SESSIONS | 3 |
| MEDIA_WHEP_BASE_URL | http://127.0.0.1:8889 |
| MEDIA_STUN_URLS | 逗号分隔，可空 |
| MEDIA_TURN_URLS | 逗号分隔，可空 |
| MEDIA_TURN_SECRET | TURN REST 共享密钥，仅服务器保存 |

如手工部署，执行迁移、同步角色权限，生成 deploy/nginx/console-gateway.conf 中的
占位密钥，安装到 /etc/nginx/snippets/cloudvirt-console.conf，文件权限 0640。
同时安装 deploy/systemd/cloudvirt-cleanup_console_sessions.service 和对应 timer，
执行 systemctl daemon-reload 以及 systemctl enable --now cloudvirt-cleanup_console_sessions.timer。
密钥用 manage.py console_gateway_key 在服务器端生成并直接写入受限配置，不应复制到日志。
多节点场景须将新 Agent 更新到每个节点，确认管理服务器和 Nginx 能访问登记的 endpoint。
HTTPS Agent 使用系统 CA 验证和节点主机名 SNI；需要内部 CA 时先安装信任链。

## 接入实际视频源

管理员在工作区「配置视频源」登记名称与流路径；这一步只绑定授权关系，
不会凭空创建视频流。普通用户不能登记或停用源。

先在服务器上发布同名路径，或由运维在媒体网关配置 RTSP 拉流。
FFmpeg 是可选发布端依赖，可单独通过 apt-get install ffmpeg 安装；安装器只安装媒体网关。
以下仅为人工验证用测试图案，不会作为平台默认数据或状态：

```bash
ffmpeg -re -f lavfi -i testsrc2=size=640x360:rate=15 -an -c:v libx264 -pix_fmt yuv420p -profile:v baseline -preset ultrafast -tune zerolatency -g 15 -bf 0 -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/lab-camera
```

界面登记流路径 lab-camera，然后点击播放。生产源应替换为实际采集/发布进程；
有摄像机凭据的配置只放在服务器。浏览器并不直接访问 RTSP，也不接受任意上游 URL。
已有 H.264 源可尝试复制码流；浏览器不支持的编码须在发布端转码。
基线 H.264、无 B 帧和短 GOP 是兼容性起点，需对实际客户端验证，不能据此保证所有浏览器。

## 指标解释

桌面显示握手耗时、首次 Canvas 绘制、可见画布更新调用次数、平均绘制调用耗时。
首次 Canvas 绘制不是屏幕物理呈现时间；更新次数不是视频 FPS；绘制调用耗时不是完整解码耗时。
仪表只包装当前实例的可见 Canvas 上下文，不修改全局 Canvas 原型或 noVNC 私有调度器。

视频显示实际接收解码 FPS、接收码率、累计丢包比例、RTP 抖动、平均抖动缓冲耗时。
没有实际帧就不会显示「正在播放」，没有数据时显示占位而非模拟指标。
这些统计不能给出真实采集端到屏幕的端到端延迟；后续需使用时间码/高速摄影等方法实测。

## 2026-10-28 验证记录

测试使用隔离源码、独立 PostgreSQL 数据库、HTTPS 18443、Agent 19100、
媒体 WHEP 18889、ICE UDP 18189。没有替换 /opt/cloudvirt 的在线应用。
临时无磁盘 KVM 虚拟机用于真实 VNC；FFmpeg 软件编码测试图用于独立视频。

环境：Ubuntu 26.04.1、内核 7.0、8 vCPU、约 7.2 GiB 内存、VMware 图形设备；
未验证可用硬件编码器。Chrome 桌面浏览器，1440×900，局域网连接。

| 验证 | 结果 |
| --- | --- |
| 前端类型检查、生产构建 | 通过 |
| 前端权限、错误、生命周期及短连接重试测试 | 14 项通过 |
| 控制台、镜像、生命周期及资源隔离回归 | 66 项通过 |
| Go 单元测试与竞态检查 | go test -race ./... 全部通过 |
| Django 迁移一致性 | 无待生成迁移 |
| 实际 noVNC | 完成 RFB 握手并绘制真实 BIOS 画面 |
| 实际独立 WebRTC | 收到 640×360、约 15 FPS 的测试视频 |
| 一次局域网采样 | 桌面握手约 50 ms、首次 Canvas 绘制约 80 ms；视频约 1.3 Mb/s |
| 前端停止视频 | srcObject 清空，无未处理 JavaScript 异常 |
| 实际安全边界 | 票据重放拒绝；公共授权入口 404；旧入口 410；缺少 CSRF 的 POST 为 403 |
| 工作区卸载 | 画布与视频元素均为 0；媒体网关 WebRTC 会话为 0 |

以上是功能联调样本，不是性能承诺、长稳测试或 30/60 FPS 验收。
尚未验证真实摄像机、音频通话、Windows/macOS/Safari、弱网、跨公网 TURN、多节点真实联调、
GPU 编码、长时间播放或并发容量。多节点目标选择有单元测试，当前真实环境只验证了一个节点。

全量后端基线 master 4436ecb 为 218 项，8 个失败、1 个错误。
本版最终使用新建数据库运行 229 项，223 项通过、5 个失败、1 个错误。
6 项失败/错误均在基线复现：用户角色权限、资源池关联/容量两个用例、
资源不足错误详情、Viewer 列表、磁盘可见性。
首轮 226 项还复现过监控对账与节点采集汇总两个基线失败，后续轮次通过，
因此这两个旧用例仍存在结果波动，不能据此声称已修复。
基线问题合计涉及：
用户角色权限、资源池关联/容量两个用例、资源不足错误详情、Viewer 列表、
监控对账、磁盘可见性、节点采集汇总。它们不能被记为本版已通过。
本版修正了旧生命周期用例中允许普通用户操作他人资源的错误假设。
另将任务活动状态约束改为固定排序，并用仅迁移状态的操作避免等价条件反复生成迁移，
不会重建现有数据库索引。

## 回退与故障排查

部署前备份数据库和 /etc/cloudvirt；磁盘镜像继续由原备份策略保护。
应用回退应同步回退前端、管理服务、Agent 和 Nginx 片段，避免协议新旧混用。
新会话表可以暂留；回退应用无需删除业务数据库、虚拟机或磁盘。
媒体为可选服务，停用 cloudvirt-media 不影响原虚拟机磁盘与网络。

先检查浏览器阶段状态与 request_id，再检查管理服务、Agent、媒体网关日志，
以及 cloudvirt-cleanup_console_sessions.timer。不要把含 Cookie、内部票据、完整 SDP、
VNC 密码或 RTSP 发布凭据的日志公开。网关不可达与权限拒绝应区分处理，不盲目重复建会话。
