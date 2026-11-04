# Ubuntu 26 安装与升级

适用于 Ubuntu 26.x amd64 宿主机。安装前确认 systemd 正常运行、硬件虚拟化已启用且可访问 `/dev/kvm`，并准备至少 1.5 GiB 内存（建议 4 GiB）和至少 8 GiB 的 `/opt` 可用空间。默认使用 HTTPS 443 和自签证书；可用 `--domain` 指定访问域名或 IP、用 `--port` 指定端口。仅在隔离环境按需使用 `--http`（默认 80）。

## 一键部署

从完整源码目录执行：

```bash
sudo bash install.sh --source "$PWD" --domain 192.168.100.100
```

将示例 IP 替换为实际访问地址。安装完成后访问该地址；首次部署的初始管理员信息由 root 在 `/etc/cloudvirt/initial-admin.txt` 查看，首次登录按提示修改密码。若使用自签证书，应先核对证书并在客户端建立信任。

```bash
sudo systemctl status cloudvirt-management cloudvirt-agent cloudvirt-worker
sudo journalctl -u cloudvirt-management -u cloudvirt-agent -u cloudvirt-worker -n 80 --no-pager
```

如果 apt 报 `qemu-kvm` 没有候选版本，确认运行的是当前仓库的安装脚本。当前脚本使用 `qemu-system-x86` 和 `qemu-utils`。

## 存储、网络与升级

新上传镜像统一写入所选存储池的 `images/user-<用户ID>/<上传ID>/`；新建系统盘、数据盘和新增数据盘写入 `vms/user-<资源所有者ID>/<虚拟机UUID>/`。目录由 Agent 自动创建，使用稳定用户 ID，不随用户名修改而变化，并拒绝符号链接。管理员给已有虚拟机增加磁盘时仍按资源所有者分组。旧上传、历史磁盘及直接使用的已有文件保留原路径，续传、校验和删除按数据库记录定位，不自动搬迁或递归清理用户目录。

虚拟机详情的磁盘页提供安装 ISO 光驱管理：管理员关机后可挂载、更换或弹出/移除 SATA sda 安装光驱。只允许本节点已校验就绪的 ISO，文件按镜像所属存储池定位；挂载后光驱优先启动，移除后恢复硬盘启动。操作不删除 ISO 文件，也不会替换占用 sda 的磁盘或修改 cloud-init 光驱。存在快照或设备级启动顺序时，节点会拒绝自动修改并提示核对。

Agent 对同一域的创建、启动、硬件、显示和快照操作串行执行；磁盘删除保留全局引用保护。控制平面仅在节点确认后提交删除标记、磁盘状态和资源释放，数据库提交采用事务。任务超时或响应丢失时须先核对原任务和节点实际状态，继续使用原幂等请求，避免重复分配。

用户的个人默认存储池统一用于新镜像注册、浏览器上传、虚拟机创建和已有系统盘定位。普通用户不能通过请求参数改用其他池或原有目录；管理员可在表单中选择池。镜像和虚拟机各自保存实际所属池，更改用户默认池只影响之后创建的资源，不会迁移旧文件。镜像相对路径以所选池目录为起点；未指定池的历史镜像仍使用节点原有镜像目录。虚拟机可从镜像记录的来源池读取镜像并将磁盘写入目标池。删除池前必须先处理其镜像、虚拟机、保留磁盘及未完成资源预留。

安装器同时安装 `cloudvirtctl`，供后续独立管理可选功能：

```bash
sudo cloudvirtctl status
sudo cloudvirtctl interface allow eno2   # 跳过该接口的管理地址/路由过滤
sudo cloudvirtctl interface protect eno2 # 恢复自动过滤
sudo cloudvirtctl enable network-bridge
sudo cloudvirtctl disable network-bridge
sudo cloudvirtctl enable destructive    # 允许磁盘清理、快照恢复等破坏性操作
sudo cloudvirtctl disable destructive
```

工具不自动安装软件包，使用已安装的服务；配置写入后自动重启对应的运行中服务。禁用 network-bridge 只停止网络配置 helper，不拆除已有网桥或虚拟机网络。网卡豁免不会迁移已有 IP 或路由，实际管理接口应继续受保护。

升级部署会保留 `cloudvirtctl` 设置的网桥模块启停状态。网络配置示例见 `deploy/network.env.example`；安装器生成的实际配置优先。`cloudvirt-network.service` 必须包含 `SupplementaryGroups=cloudvirt`，使受限 helper 可访问 `/var/lib/cloudvirt/network` 的上级目录；不要通过放宽配置目录为全局可写来解决权限问题。

安装或升级时可重复指定 `--bridge-allow-interface eno2 --bridge-allow-interface eno3`，使这些网卡跳过管理地址和路由的自动过滤。配置保存在 `/etc/cloudvirt/network.env` 的 `CLOUDVIRT_BRIDGE_ALLOWED_INTERFACES`，重复安装保留已有豁免；移除豁免需编辑该变量并重启 `cloudvirt-network`。接口已加入其他网桥或聚合时仍禁止接入。该选项不迁移已有地址、路由或网络配置，请只指定已确认可用于业务桥接的接口；桥接实际管理网卡可能中断宿主机连接。

如需在默认数据目录以外创建目录存储池，安装或升级时重复传入允许的存储根目录：

```bash
sudo bash install.sh --source "$PWD" --domain 192.168.100.100 \
  --storage-root /mnt/cloudvirt-vms --storage-root /srv/vm-disks
```

安装器会创建目录、授予节点 Agent 写入权限，并将路径加入 `CLOUDVIRT_STORAGE_ROOTS` 和 systemd 写入白名单。随后管理员可在“存储池”页面选择这些根目录或其子目录建池、分配可使用的用户，并为每个节点指定一个默认池，也可为每位用户指定个人默认池。个人默认优先于节点默认；用户有多个授权池且均无默认时，创建时须明确选择。根目录须是独立、非符号链接的绝对路径；挂载的文件系统应先可用。已有实例保留原落盘位置，只有新建实例会使用选定池。

仓库内的 `offline/linux-amd64` 包会自动优先使用；也可指定 `--offline-dir /path/to/linux-amd64`。包和源码依赖锁均通过 SHA-256 校验，不匹配时停止安装。该包包含 Node.js、Python wheels、npm 缓存、Go vendor；从本地完整源码执行 `--source` 不会访问 GitHub 克隆源码。apt 软件包仍取自系统配置的仓库或镜像。重新生成方式见 [offline/README.md](../offline/README.md)。

按需增加 --enable-ovs、--allow-destructive；重复安装保留数据库与密钥并备份，迁移前停止控制平面任务。不要在无维护窗口的生产环境直接重装。
