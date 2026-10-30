# CPU 使用率采集

Agent 首次资源请求启动进程级采样器，每秒读取 Linux /proc/stat 聚合 cpu 行。两次计数器差值计算 busy/total；idle 与 iowait 作为空闲，guest/guest_nice 已包含在 user/nice 中，不重复累加。请求不 sleep，不按每个客户端启动采样器。

首次尚无差分、计数回退、读取失败或样本超过 5 秒时 Agent 返回 null；真实空闲返回 0。资源接口新增 cpu_usage_percent 与 cpu_sampled_at。管理端校验数值范围、有限性与时区时间，旧 Agent 缺字段保持兼容。

管理端 30 秒节点采集保存最近样本。管理员总览仅统计未过期、在线/降级且 CPU 样本在 60 秒内的节点，按逻辑核数加权，并返回 cpu_sampled_nodes；部分节点无数据时只计算有效节点，不伪装全量平均。普通用户总览不暴露宿主机 CPU 汇总。

节点详情展示有效使用率及采样时间。Agent 重启后短暂预热，最多等待下一次节点采集及前端刷新。当前仅补齐实时指标，未引入历史时序存储，不伪造 CPU 趋势。
