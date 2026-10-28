# Ubuntu 26 一键部署

支持 Ubuntu 26.x amd64、systemd 与可用的 /dev/kvm。最低 1.5 GiB 内存和
8 GiB 可用磁盘，建议至少 4 GiB 内存，并预留虚拟机镜像/磁盘实际需要的空间。
如果宿主机本身是虚拟机，需要先在上层开启嵌套虚拟化。

## 使用完整源码包部署

把包含 install.sh 的完整源码包上传并解压到 Ubuntu，然后在项目根目录执行：

    sudo bash install.sh --enable-ovs --allow-destructive

指定域名或服务器 IP：

    sudo bash install.sh --domain cloudvirt.example.com --enable-ovs --allow-destructive

这会安装依赖、构建三组件、初始化 PostgreSQL、生成密钥/证书、迁移数据库、
创建首个管理员、注册本机节点、配置 nginx/systemd 与采集/对账 timer。
--enable-ovs 配置独立 ovsbr0、DHCP 和出口 NAT，不把物理管理网卡加入网桥。
--allow-destructive 显式打开 Agent 强停/删除能力，默认关闭。

省略这两个参数可只部署控制台与 libvirt 默认 NAT：

    sudo bash install.sh

安装完成后访问打印的 HTTPS 地址。证书默认自签名，浏览器会提示不受信任；
在受控环境核对证书后访问，正式域名建议替换为可信证书。

    sudo cat /etc/cloudvirt/initial-admin.txt

管理员用户名为 admin，初始口令随机生成并保存在上述 root-only 文件；
首次登录必须改密。重跑不会重置已经存在的管理员，也不会删除数据库或客体磁盘。
如果先前没有由安装器创建口令文件，已有管理员应使用原口令。

--http 可用于受控测试环境：

    sudo bash install.sh --http --port 8080

## 完整源码与远端源码

默认优先使用 install.sh 所在目录的完整项目，可使用 --source /path/to/project 指定。
这会包括当前本地 UI 优化、权限校验和部署适配。

如果只复制 install.sh 且当前目录没有源码，脚本会尝试拉取：

    https://github.com/trep123/cloudevirt.git
    master

可通过 CLOUDVIRT_REPO_URL / CLOUDVIRT_REPO_REF 改变来源。远端拉取只包含已经推送的代码。
UI 优化与安装器一并维护在 master 主分支，可使用完整部署包，
或从该分支获取源码后执行 install.sh。指定其他分支时，请确认包含 scripts/install_ovs.sh。

安装过程需要访问 Ubuntu 软件源、Python 包源、Node.js 下载源、npm registry，
以及 Go 模块/工具链源。保留锁定依赖版本；下载或版本不可用会明确失败，
不会偷偷替换 Django/DRF 依赖版本。

## 参数

| 参数 | 用途 |
| --- | --- |
| --source DIR | 指定完整本地源码目录 |
| --domain HOST | 访问域名或 IPv4，默认识别主网卡地址 |
| --port PORT | Web 端口，默认 HTTPS 443 |
| --http | 使用 HTTP，未指定端口时为 80 |
| --enable-ovs | 启用独立 OVS DHCP/NAT |
| --allow-destructive | 启用 Agent 强制停止和删除操作 |
| --help | 只输出帮助 |

可选网络变量：

    sudo env CLOUDVIRT_UPLINK=ens3 \
      CLOUDVIRT_OVS_SUBNET=192.168.160.0/24 \
      CLOUDVIRT_OVS_GATEWAY=192.168.160.1 \
      CLOUDVIRT_OVS_DHCP_START=192.168.160.100 \
      CLOUDVIRT_OVS_DHCP_END=192.168.160.200 \
      bash install.sh --enable-ovs

默认出口从系统默认路由识别，不依赖 ens18。子网与宿主机现有路由重叠时拒绝部署。
默认 OVS 防火墙阻止客体访问 RFC1918 管理网、链路本地地址与宿主机 TCP 服务，
允许 DHCP、ICMP 与经配置出口访问公网。已有防火墙依然有效。
已启用的 UFW 会增加 Web 端口和指定 OVS 范围的规则，不启用或关闭整机防火墙。
云厂商安全组需单独放行 Web 端口，内部 8000/9100 不对外开放。

现有 OVS 网络的子网、网关或上联网卡发生变化时，安装器拒绝静默重编号；
应先制定迁移方案。DHCP 地址池可通过参数重配，服务与数据库元数据同步更新。

## 文件与服务

| 路径 | 内容 |
| --- | --- |
| /opt/cloudvirt | 应用源码、Python venv、独立 Node.js、Agent 二进制 |
| /etc/cloudvirt/management.env | 后端配置，root:cloudvirt 640 |
| /etc/cloudvirt/agent.env | Agent 配置，root:cloudvirt-agent 640 |
| /etc/cloudvirt/install-secrets.env | 安装器持久密钥，root 600 |
| /etc/cloudvirt/tls | 自签名 TLS 证书与私钥 |
| /var/lib/libvirt/images/cloudvirt/images | 真实 OS 镜像导入目录 |
| /var/lib/libvirt/images/cloudvirt/disks | 虚拟机磁盘目录 |
| /var/backups/cloudvirt | 重跑时的源码和 PostgreSQL 备份 |
| /var/www/cloudvirt | 前端构建产物 |

不自动下载虚拟机 OS 镜像。部署后将已获得的镜像放入 images 目录并在镜像页面登记。
也可直接使用镜像页面的浏览器分片上传，上传后异步校验，详见 [镜像上传说明](IMAGE_UPLOADS.md)。
Agent 使用独立 cloudvirt-agent 系统账号，通过 libvirt/kvm 组访问宿主机能力；
管理后端、worker 与定时作业使用 cloudvirt 账号。

    sudo systemctl status cloudvirt-management cloudvirt-agent cloudvirt-worker
    sudo systemctl list-timers 'cloudvirt-*'
    sudo journalctl -u cloudvirt-management -u cloudvirt-agent -u cloudvirt-worker -n 100
    sudo journalctl -u cloudvirt-collect_node_status -u cloudvirt-reconcile -n 100
    sudo nginx -t

修改 environment 文件后重启对应服务。切换域名/HTTP 模式时安装器会更新访问来源、
安全 Cookie 与代理配置，并保留其余配置及密钥。
更换域名需同步替换匹配的新证书，已有证书不会自动覆盖。

如果重跑中途失败，应用服务可能维持停止状态。检查输出所标记的 STEP 后重跑；
安装器不会假装回滚数据库迁移，也不会自动恢复旧版本代码。备份可供人工恢复。
这是一键安装与同目录重部署脚本，不是跨版本迁移或无停机升级工具。

## 当前验证范围

Ubuntu 26 的 QEMU 依赖使用明确的 qemu-system-x86 包，而不使用可能为虚拟包的
qemu-kvm 名称；安装后检查 /usr/bin/qemu-system-x86_64 是否存在。

安装脚本与 OVS helper 已进行 Bash 语法检查、帮助入口检查和内嵌 Python 语法检查。
本次 Windows 环境未执行 Ubuntu apt 安装、systemd 启动或真实 KVM/OVS 验收。
运行时必须通过 Agent、Django、nginx 健康检查以及本机节点采集后才打印部署完成。

依赖安装方式参考 [Ubuntu 官方 libvirt 文档](https://ubuntu.com/server/docs/how-to/virtualisation/libvirt/)。
