# 虚拟机显示分辨率

管理入口：虚拟机详情 → 硬件 → 虚拟机显卡与启动显示尺寸。创建向导的高级硬件配置和部署模板也支持 `video_model`、`video_width`、`video_height`。

- 旧实例可能使用 libvirt 默认的 Cirrus 显卡。新建实例显式使用标准 VGA（64 MiB），可选择节点实际支持的 VirtIO GPU。
- 管理员可对已确认关机的实例提交显示配置任务。节点再次校验关机状态，更新原有域定义中的单个显卡型号与显示尺寸，保留磁盘、网卡、UEFI/NVRAM、设备地址等其他配置。多显卡与直通实例拒绝自动修改。
- 支持 640×480 至 3840×2160 的整数尺寸。改动持久保存，下次启动使用；不会自动关机、重启或执行客体命令。
- libvirt 的 `model/resolution` 是显卡提供给客体的最小/首选显示模式，不是对 GNOME、KDE 或 Windows 桌面的强制分辨率策略。用户登录后的桌面配置可能覆盖它。Linux 建议 VirtIO；Windows 更换显卡前应准备驱动。
- 启动后，在客体“设置 → 显示”中选择目标模式；noVNC 下方显示实际 framebuffer 尺寸。客体未切换时，不能将任务成功或网页缩放当作桌面分辨率已改变。
- 暂不提供通用在线强制切换：现有 QEMU VNC 和未安装桌面控制组件的客体没有跨操作系统的可靠接口。若后续需要在线强制切换，需要经过授权的客体桌面组件，分别适配 X11、Wayland 和 Windows 会话。

API：`GET/POST /api/v1/admin/vms/{id}/display/`。GET 返回节点持久显卡配置与可用型号；POST 接收 `{ "model": "virtio", "width": 1920, "height": 1080 }`，返回异步任务。写入仅限管理员，校验对象范围、节点可用性、状态新鲜度、并发任务及输入范围，并记录提交审计。任务结果明确 `guest_mode_confirmed: false`。

参考：[libvirt Video devices](https://libvirt.org/formatdomain.html#video-devices)。

## 独立控制台与快捷键

控制台入口统一打开 `/admin/vms/{id}/console` 或 `/app/vms/{id}/console`。页面保持登录和对象授权边界，列表与详情不再嵌入画面。按实际 framebuffer 宽高比构建视口，页面全屏可用 Esc 退出；浏览器全屏保留完整桌面比例，不裁剪或拉伸。

Ctrl+C/X、Ctrl+V 支持文本复制、剪切、粘贴；macOS 可用 Command，Linux 终端使用 Ctrl+Shift+C/V。浏览器原生 paste 事件提供文本，不后台轮询本地剪贴板。只有用户明确请求复制后，收到的客体剪贴板内容才会写入本地剪贴板；拒绝权限或未收到客体数据时提示原因。仅支持文本，不传文件或图片。

硬件页与创建向导提供 `clipboard` 开关，默认关闭。节点通过 QEMU 支持的字符设备检测能力，使用 `qemu-vdagent` 通道与 `com.redhat.spice.0` 端口，并显式启用 `<source><clipboard copypaste="yes"/></source>`。既有实例必须正常关机后保存，再启动生效；不自动停止实例。不替换已有 SPICE 通道或直通配置。

客体需安装并运行 SPICE vdagent（Ubuntu：`sudo apt install spice-vdagent`，然后重新登录图形桌面；Windows 需要对应的驱动及代理）。浏览器复制需要受信任的 HTTPS 和剪贴板写入权限。通道存在不等于代理已就绪，不宣称粘贴已经被客体应用接收。

参考：[libvirt Channel device / qemu-vdagent](https://libvirt.org/formatdomain.html#channel)。
