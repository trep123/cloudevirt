# 直接共享正常平台页面

顶栏默认入口为“开启页面共享”，无需进入服务端工作台窗口。用户点击后，在浏览器原生选择框中选择**当前平台标签页**，随后继续在正常页面操作。观看者通过复制出的链接只读观看，包括当前标签页内的列表、详情、虚拟机控制台和页面切换。

浏览器必须由用户明确授权捕获。不要选择其他包含隐私信息的标签页。当前实现仅共享画面，不采集麦克风或声音。页面共享不会自动播放自己的视频。

关闭、刷新页面、退出平台、点击“停止共享”，或使用浏览器自带的停止共享按钮，都会结束发布。在网络中断、浏览器崩溃等情况下，服务器在 90 秒发布租约到期后回收，后台默认每 15 秒检查。观看链接最长有效 12 小时，发布者必须持续在线。此模式已不要求关闭浏览器后继续显示。

## 部署与权限

沿用现有媒体网关、只读观看页面和 `console.use_workspace` 发布权限。直接页面共享无需 Chromium/Xvfb 服务端工作台组件，也不依赖 `WORKBENCH_ENABLED`。需要 HTTPS、浏览器 `getDisplayMedia` 和 WebRTC，以及已安装的 MediaMTX（完整安装器 `--enable-media` 或原有 `--enable-workbench` 均可安装媒体网关）。

升级应用源码后执行 Django 数据库迁移，重新构建并部署前端，重启管理后端。新增迁移 `console.0005_tab_shares`。保留旧工作台 API 供兼容使用，但顶栏入口改为直接共享当前页面，旧 `/admin/workbench`、`/app/workbench` 地址跳转至正常首页。

每个账号最多同时发布一个页面，默认全站最多 8 个浏览器发布者，配置 `TAB_SHARE_MAX_PUBLISHERS`。发布接口绑定当前用户及其登录会话，匿名观看凭证无法创建、续租或停止发布。注销立即撤销观看授权，密码/权限变更由后台回收。

## 接口

- `GET /api/v1/console/tab-shares`：发布者 ICE 配置。
- `POST /api/v1/console/tab-shares`：提交浏览器 offer、UUID `request_id`；代理本地 WHIP，返回 SDP answer、服务端 ID 和只读观看链接。相同请求不重复创建。
- `POST /api/v1/console/tab-shares/requests/{request_id}`：续租，前端每 20 秒调用。
- `DELETE /api/v1/console/tab-shares/requests/{request_id}`：撤销分享并删除对应 WHIP 会话。

观看接口保持 `/console/broadcasts/{id}/watch` 与 `/console/watch-sessions/{id}`。媒体网关发布 URL 及内部资源 URL 不返回客户端，接入仍通过同源 Session、CSRF 和权限检查。

## 验证

2026-10-28：独立 PostgreSQL 测试库中控制台 37 项测试通过，含 9 项新增页面发布、观看权限、停止、崩溃过期、注销和回收测试。前端类型检查、生产构建与 17 项既有测试通过。

隔离环境中使用真实 Chromium `getDisplayMedia` 标签页捕获与 WHIP 发布，观看端成功通过 WHEP 播放 1440×900 视频；普通应用页面切换时发布继续，停止后仍保持正常平台登录。测试使用专用临时账号，未捕获生产管理员页面。

浏览器授权机制见 [getDisplayMedia 文档](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia)。
