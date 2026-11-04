# Ubuntu 26 卸载说明

从完整源码目录运行。需要保留虚拟机、磁盘或数据库时，使用普通卸载；需要永久清理时，先预览完全清理计划，并将要保留的备份复制到清理范围之外。两种脚本默认都只预览。

## 完全清理

另提供独立的 **完全清理** 入口 `uninstall-full.sh`。它会删除平台虚拟机、平台生成的磁盘/上传镜像及缓存、数据库与角色、平台服务/定时任务、托管网桥、OVS/NAT 集成、应用副本、配置/密钥、日志和部署备份，并移除可追溯到安装器新增的软件包。项目源码 checkout 和其中的离线依赖包始终保留。

```bash
# 从完整项目目录运行，默认只展示计划
sudo bash uninstall-full.sh --dry-run

# 以下命令会永久删除业务数据，只在确认预览清单后使用
sudo bash uninstall-full.sh --apply --confirm DELETE-CLOUDVIRT
```

新安装在 `/var/lib/cloudvirt-installer` 记录每次安装前后新增的软件包、服务账号和存储目录；升级时合并新增包记录，不把两次升级之间自行安装的软件计入。安装失败或旧安装缺少完整来源记录时，脚本拒绝自动清包；需依据实际 apt 安装历史核对，并用 `--packages 包名1 包名2` 明确指定。软件包清理前会模拟依赖删除，若会连带移除清单外的软件包则中止，不执行无边界的 `apt autoremove`。

完全清理须在应用和数据库仍可读取时执行，不能先运行保数据卸载再要求其自动推断所有外部文件。数据库只支持安装器本机的 `cloudvirt` 数据库与角色；存在其他虚拟机、共享数据库、未知网桥端口、路径重定向、嵌套挂载或项目目录冲突时会拒绝相应清理。直接挂载的外部原始系统盘、手动登记的外部原始镜像以及外部目录中的未知文件保留并列入预览，防止把“引用文件”误当作平台创建的文件。不会重置共享的运行时 IP 转发值。

## 保留业务数据的卸载

`uninstall.sh` 为 **保留业务数据** 的控制平面卸载，使用方式如下：

```bash
sudo bash uninstall.sh             # 默认只展示计划
sudo bash uninstall.sh --dry-run   # 明确预览
sudo bash uninstall.sh --apply     # 真正卸载控制平面
```

### 移除范围

- 停止并禁用 CloudVirt API、worker、Agent、已知定时任务及旧版控制平面服务，删除其明确列出的 systemd 单元和安装器 Agent drop-in。
- 移除 CloudVirt nginx 站点及控制台、安全响应头、HSTS snippet。先备份并校验 nginx；移除后再次校验，其他站点仍依赖这些 snippet 时恢复配置并中止，不停止共享 nginx。
- 只递归删除固定白名单中的 /opt/cloudvirt/apps、frontend、.venv、runtime、offline 和 /var/www/cloudvirt。拒绝符号链接/重定向父目录和内部挂载点，不接受自定义删除路径。
- 仅接受存在有效 root-owned 0600 install-secrets.env 标记的安装器部署。与安装器共用 flock，避免并发。

### 明确保留

- PostgreSQL 服务、cloudvirt 数据库/角色和数据；不会执行 DROP DATABASE/ROLE。
- 所有虚拟机定义及运行状态、系统盘/数据盘/ISO、快照、libvirt 存储池、外部存储配置。
- /etc/cloudvirt（密钥、TLS、初始账号等）、/var/lib/cloudvirt、/var/lib/libvirt、/opt/cloudvirt/backups、/var/backups/cloudvirt 及源码 checkout。
- cloudvirt-network、cloudvirt-ovs-net、cloudvirt-ovs-dhcp、/opt/cloudvirt/services 下二进制及源文件。保留这些网络依赖使现有虚拟机网络重启后仍可恢复。
- 管理网卡/业务网桥/OVS 端口、DHCP、NAT/nftables、UFW 规则、IP 转发设置、系统软件包和服务账号。不会自动解绑网卡或关闭 libvirt。
- nginx 默认站点及其他管理员站点，安装和卸载均不改动。
- 自定义 systemd override、源码和辅助文档可能保留，避免误删人工部署内容；这不是清空宿主机的脚本。

### 备份与失败恢复

执行模式创建 root-only /var/backups/cloudvirt/uninstall-XXXXXXXX，保存配置、相关 systemd 单元和 nginx 文件。备份包含敏感配置，不得公开。

卸载不删除业务数据，因此没有 --purge-data。应用目录删除不可通过产品界面撤销，但可从完整源码重新安装；复用保留的安装密钥、数据库和磁盘。卸载后 API/控制台不可用，虚拟机仍由 libvirt 运行，管理员可通过 virsh 管理。
