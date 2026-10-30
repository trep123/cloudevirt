# Ubuntu 26 安装检查与卸载说明

## 本次安装脚本检查

- 对更新后的 install.sh、uninstall.sh 执行 Bash 语法检查，验证现有主机的 HTTPS API 与 HTTP 重定向；未执行安装或卸载流程。
- 实际 Ubuntu 26 主机的软件包索引中，qemu-system-x86、qemu-utils、libvirt-daemon-system、libvirt-daemon-config-network、Python 3.14、Go 均有候选版本；没有重新使用无候选的 qemu-kvm 虚拟包。
- 修复升级部署在数据库迁移前遗漏停止 cleanup_account_batches 定时器/任务的问题。
- 修复升级后网络 helper 仅 enable --now、未重启导致仍运行旧版本的问题。
- 应用/配置/Web 根目录校验拒绝符号链接及重定向父目录。
- 安装时保留 nginx 默认站点和已有站点，由 CloudVirt 的 `server_name` 处理指定域名；同时检查 API、前端入口及网络 helper。
- 卸载时将 CloudVirt 的控制台、安全响应头和 HSTS snippet 一起备份并移除；nginx 校验失败时恢复这些文件。
- 验证范围为语法、当前主机包可用性、现有服务和 HTTP 响应；没有在全新系统上重装。镜像源、外网下载、硬件虚拟化、磁盘空间等仍由安装时实际检查决定。

## 安装

从完整源码目录执行：

```bash
sudo bash install.sh --source "$PWD" --domain 192.168.100.100
```

按需增加 --enable-ovs、--allow-destructive；重复安装保留数据库与密钥并备份，迁移前停止控制平面任务。不要在无维护窗口的生产环境直接重装。

## 卸载：本次只生成，未执行

```bash
# 以下仅为将来的使用说明，本次均未执行：
sudo bash uninstall.sh             # 默认只展示计划
sudo bash uninstall.sh --dry-run   # 明确预览
sudo bash uninstall.sh --apply     # 真正卸载控制平面
```

### 移除范围

- 停止并禁用 CloudVirt API、worker、Agent、已知定时任务及旧版控制平面服务，删除其明确列出的 systemd 单元和安装器 Agent drop-in。
- 移除 CloudVirt nginx 站点及控制台、安全响应头、HSTS snippet。先备份并校验 nginx；移除后再次校验，其他站点仍依赖这些 snippet 时恢复配置并中止，不停止共享 nginx。
- 只递归删除固定白名单中的 /opt/cloudvirt/apps、frontend、.venv、runtime 和 /var/www/cloudvirt。拒绝符号链接/重定向父目录和内部挂载点，不接受自定义删除路径。
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
