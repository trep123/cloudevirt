# 平台功能规格差距审查

以《虚拟化管理平台详细模块功能规格说明书》为目标，以当前源码为基线。下表中的“已有”指能在代码中找到实际入口或执行链路，不能代替部署验收。

| 规格章节 | 已有能力和代码入口 | 缺口与下一步 |
| --- | --- | --- |
| 2–4、25 身份、导航、会话、权限 | accounts、common permissions/scope、LoginPage；账号管理、角色、数据范围和登录限流 | 逐条核验管理员与普通用户的会话边界、撤销、敏感操作再认证；不能用菜单可见性代替对象授权 |
| 5 总览 | 前端总览、monitoring、节点与任务统计 | 核验管理员与个人口径、历史趋势及过期数据标识 |
| 6–7、30 集群、节点、Agent | infrastructure Cluster/ClusterNode、nodes、Go Agent | 集群当前以组织关系为主；补齐维护排空、Agent 身份与证书轮换、版本升级及兼容性验收 |
| 8、32 虚拟机及核心流程 | instances、VmWizard、硬件配置、操作执行器、回收与保留盘 | 核验创建预检与执行一致性、变更失败回滚、独立 VM 克隆和删除后的资源对账 |
| 9、27 调度、配额、预留 | infrastructure placement、ResourceReservation、ResourcePool、common quota | 补齐跨节点约束评分、GPU/PCI 资源调度、项目配额和均衡；未实现的能力不应显示为可用 |
| 10–11 存储、虚拟磁盘 | storage_api、ManagedStoragePool、Disk、Agent storage | 逐个验收后端能力；磁盘迁移和存储维护需要独立任务、失败恢复及真实设备验证 |
| 12–13 网络与 IP | networks 的网桥、NIC、IPPool/IPLease，Agent 网络执行 | 补齐 Bond 与网络安全策略；静态租约唯一约束不等于对外部设备的地址冲突检测 |
| 14–15 镜像、模板与初始化 | images 上传与校验、TemplateVersion、VM 初始化配置 | 验收大文件传输、下架与引用保护；Windows 初始化须独立验证，不能沿用 Linux 的交付结论 |
| 16 快照 | infrastructure SnapshotsView 和 Agent 执行 | 当前核心为受管 qcow2 的关机内部快照；扩展前先验证一致性与链依赖，内部快照不算独立备份 |
| 17–19 备份、迁移、HA | 现有任务、监控、集群可复用 | 缺独立备份与恢复验证闭环、迁移前检查与故障补偿、HA 仲裁和节点隔离；须在多节点环境验证 |
| 20 Web 控制台 | console 会话与前端控制台 | 验收过期撤销、对象授权、审计，以及连接失败时的提示 |
| 21–22 监控与告警 | monitoring Alert、ReconciliationRun/Diff、MonitoringPage | 缺完整规则、通知投递、降噪与确认闭环；明确指标保留周期和聚合口径 |
| 23–24 任务、事件、审计 | tasks worker、TaskEvent、AuditEvent | 本轮限制任务参数和结果输出，并补齐取消时间；后续核验任务重放安全、错误文本脱敏和审计保留策略 |
| 26 项目与多租户 | 用户对象范围、资源池可复用 | 缺独立 Project/ProjectMember 和项目级资源归属；资源池不能替代租户隔离 |
| 28 API 与自动化 | 现有 DRF API、节点 API | 缺面向外部的细粒度凭证生命周期、Webhook 投递、自动化任务与受控 Agent/MCP 接入 |
| 29 系统设置 | ConsoleConfiguration、SettingsView | 补服务健康、邮件通知、平台自身备份及升级回滚 |
| 31、33–36 UI、数据、非功能与验收 | 现有共享布局、模型约束、安装脚本及测试 | 统一危险操作确认、加载和权限状态；按单节点、多节点、故障注入分别记录实测结论 |

实施顺序：先处理 API 数据暴露与资源权限，再验收创建、删除、存储和网络流程；随后完成备份恢复与告警通知。迁移和 HA 在备份可恢复、节点隔离和多节点环境就绪后推进；项目与自动化应先建立权限模型和凭证边界。

任务 API 保留 `payload` 和 `result` 响应字段，但仅返回允许公开的诊断标量。worker 仍读取原始 JSON。取消任务会记录结束时间并清除待重试时间。
