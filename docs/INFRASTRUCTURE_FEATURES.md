# 原未开放功能的实施与升级

本次增加集群、资源池、存储池、快照与系统设置。所有页面读取真实数据库或节点数据，未采集、失败和权限不足分别显示；不生成示例资源。

## 已实现能力

| 入口 | 页面与接口 | 约束 |
| --- | --- | --- |
| 集群 | `/admin/clusters`；`GET/POST /api/v1/admin/clusters/`，`POST/DELETE .../{id}/` | 名称唯一；节点只能归属一个集群；编辑成员、节点详情跳转、健康及配置量汇总；删除前须移出成员和资源池 |
| 资源池 | `/admin/pools`；`/api/v1/admin/resource-pools/` | 集群内分配已有虚拟机，配置 vCPU/MiB/GiB 上限；事务内校验成员与配置总量，不能跨集群或重复分组 |
| 存储池 | `/admin/storage-pools`；`GET/POST /api/v1/admin/nodes/{id}/storage-pools/` | 实际 libvirt 池类型、容量、活动状态；能力清单目前仅允许目录池创建，名称以 cv- 开头 |
| 快照 | `/admin/snapshots`、`/app/snapshots`、虚拟机详情的快照标签；`GET/POST /api/v1/snapshots/instances/{id}/` | 普通用户只能读取自己且节点授权允许的实例；变更仅管理员可执行 |
| 系统设置 | `/admin/settings`；`GET/PUT /api/v1/admin/settings/` | 全体普通用户默认资源配额、存储使用率提示阈值；版本号防止覆盖其他管理员的修改 |

集群和资源池是平台组织关系，不会自动执行迁移、HA、宿主机资源隔离或授权扩展。
资源池限额约束已分配成员的配置总量；新建虚拟机仍走原向导，创建后可分配到资源池。
关机虚拟机仍占用资源池限额。现有硬件配置尚不支持编辑；未来增加硬件编辑时必须复用池上限校验。

新建目录池的位置由 Agent 决定，为 `CLOUDVIRT_DISK_DIR/{pool-name}`。浏览器不能指定任意路径、设备、网络挂载或可执行命令。
新建池不会自动迁移已有磁盘，当前虚拟机创建仍使用默认受管磁盘目录；尚未增加按池选择磁盘位置、池删除、激活/停用和 LVM/NFS 编排。
同一文件系统上的多个池共享容量，页面不把它们相加充当节点总容量。

## 快照执行边界

- 仅支持实际关机状态、受管目录内的 qcow2 磁盘及 libvirt 内部快照。创建、恢复和删除都通过 worker 异步执行。
- 前端明确显示目标虚拟机、快照和影响；所有写请求携带幂等键，相同请求复用原任务，参数变化返回 409。
- 后端与节点均校验条件。节点最终执行时再次读取 libvirt 状态和磁盘定义；名称使用 cv- 前缀。
- 创建不需要破坏性开关；恢复和删除必须设置 `CLOUDVIRT_ALLOW_DESTRUCTIVE=true`（安装器 `--allow-destructive`）。
- 恢复覆盖快照后的磁盘变更，保持虚拟机关机；存在子快照时必须先删除子快照，禁止隐式级联。
- 其他格式或外部快照仅展示。内部快照与原磁盘共享故障域，不是独立备份。
- 任务不自动重试。执行中断或调用超时时，可能已执行；先核对节点实际状态，再发起新的已确认操作。任务中心禁止直接重放快照任务。
- 所有提交和成功执行均写入审计，失败原因由任务中心保存。

## 设置生效规则

默认使用 `USER_QUOTA_*` 环境变量和 80% / 90% 存储阈值。保存后数据库配置覆盖默认值，Web 和 worker 无需重启。
降低配额不会删除已有资源；超过新上限的普通用户会在下一次创建时被拒绝。管理员不受普通账号配额限制。
存储阈值用于存储池页面的警告/高风险提示，不会改变已有监控告警状态或自动执行清理。
API/数据库/节点令牌等管理凭据不通过设置接口返回或修改。

## 升级

先备份数据库与磁盘，在保留原配置和启动参数的前提下重新运行更新后的 install.sh。
安装器会构建前端和 Agent、执行数据库迁移并重启管理服务；必须同步升级管理端、worker 和所有相关节点 Agent。
不应只替换前端静态文件，否则新接口不可用。

手动部署至少完成：

1. 停止管理服务和 worker，保留正在运行的虚拟机。
2. 安装本次代码，构建前端及 Linux Agent。
3. 在原管理服务环境配置下运行 `python manage.py migrate --noinput` 和 `python manage.py sync_roles`。
4. 更新前端静态文件和节点 Agent，重启 management、worker、agent 服务。
5. 在验证环境执行下列测试，检查实际 libvirt 结果及普通用户越权请求。

## 验证

已完成前端类型与生产构建、修改 Python 文件的 Ruff 检查、Linux/amd64 Agent 交叉编译。
新增后端权限、成员冲突、限额、设置版本和快照幂等测试；新增 Agent 认证、破坏性开关、路径拒绝及 XML 解析测试。
按当前环境限制，测试代码未运行，数据库迁移及真实 Ubuntu/libvirt/KVM 操作尚未验证。

在具备项目依赖的验证环境运行：

```sh
cd apps/management
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.infrastructure
cd ../../frontend
npm test
npm run build
cd ../services/virt-node-agent
go test ./...
```

libvirt 行为依据：[virsh 命令说明](https://www.libvirt.org/manpages/virsh.html)、[存储池格式](https://libvirt.org/formatstorage.html)。
