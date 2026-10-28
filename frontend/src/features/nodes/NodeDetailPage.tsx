import { useEffect, useState } from "react";
import { api } from "../../api";
import { navigate } from "../../app/router";
import { PageHeader, ResourceStatCard } from "../../components/ConsoleUI";
import {
  Card,
  DescList,
  EmptyState,
  ErrorBanner,
  LoadingState,
  Meter,
  StatusBadge,
  Tabs,
  describeError,
  formatBytes,
  formatRelative,
  formatTime,
  statusLabel,
  statusTone,
} from "../../components/ui";
import type { Node, Instance, Paginated } from "../../types";
const TABS = ["概览", "虚拟机", "存储", "网络", "监控", "代理与诊断"];
export function NodeDetailPage({ id }: { id: number }) {
  const [node, setNode] = useState<Node | null>(null),
    [instances, setInstances] = useState<Instance[]>([]),
    [error, setError] = useState<string | null>(null),
    [tab, setTab] = useState("概览");
  useEffect(() => {
    let alive = true;
    Promise.all([
      api.request<Node>("/nodes/" + id),
      api.request<Paginated<Instance>>("/instances?node=" + id),
    ])
      .then(([n, i]) => {
        if (alive) {
          setNode(n);
          setInstances(i.results);
        }
      })
      .catch((e) => {
        if (alive) setError(describeError(e));
      });
    return () => {
      alive = false;
    };
  }, [id]);
  const gb = (mib: number | null) =>
    mib === null ? "—" : (mib / 1024).toFixed(1) + " GB";
  const memUsed =
    node && node.memory_total_mib && node.memory_available_mib !== null
      ? Math.round(
          ((node.memory_total_mib - node.memory_available_mib) /
            node.memory_total_mib) *
            100,
        )
      : null;
  const diskUsed =
    node && node.storage_total_bytes && node.storage_free_bytes !== null
      ? Math.round(
          ((node.storage_total_bytes - node.storage_free_bytes) /
            node.storage_total_bytes) *
            100,
        )
      : null;
  return (
    <>
      <PageHeader
        back={{ label: "物理节点", onClick: () => navigate("/admin/nodes") }}
        title={node?.name || "物理节点"}
        meta={node ? <StatusBadge status={node.status} /> : null}
        description={
          node ? (
            <>
              <span className="mono">{node.endpoint}</span> ·{" "}
              {node.is_schedulable ? "可调度" : "不可调度"} · 最近心跳{" "}
              {formatRelative(node.last_seen_at) || "—"}
            </>
          ) : (
            "读取节点信息"
          )
        }
      />
      <ErrorBanner message={error} />
      {node ? (
        <>
          {node.resource_is_stale ? (
            <div className="banner banner-info">
              采样已过期 · 最后成功采样 {formatTime(node.resource_sampled_at)} ·
              心跳 {formatTime(node.last_seen_at)}
            </div>
          ) : null}
          <div className="resource-stats">
            <ResourceStatCard
              label="连接状态"
              icon="network"
              tone={node.status === "ONLINE" ? "ok" : "warn"}
              value={
                <span className={`stat-status tone-${statusTone(node.status)}`}>
                  {statusLabel(node.status)}
                </span>
              }
              note={`${node.agent_version || "Agent 版本未知"} · 连续失败 ${node.consecutive_failures} 次`}
            />
            <ResourceStatCard
              label="逻辑 CPU"
              icon="cpu"
              value={
                <>
                  {node.cpu_total ?? "—"}
                  <span className="stat-unit"> 核</span>
                </>
              }
              note="尚未采集 CPU 使用率"
            />
            <ResourceStatCard
              label="可用内存"
              icon="memory"
              value={gb(node.memory_available_mib)}
              note={`总量 ${gb(node.memory_total_mib)} · 已用 ${memUsed ?? "—"}%`}
            >
              <Meter value={memUsed} />
            </ResourceStatCard>
            <ResourceStatCard
              label="剩余存储"
              icon="disk"
              value={formatBytes(node.storage_free_bytes)}
              note={`总量 ${formatBytes(node.storage_total_bytes)} · 已用 ${diskUsed ?? "—"}%`}
            >
              <Meter value={diskUsed} />
            </ResourceStatCard>
          </div>
          <Tabs label="节点详情" tabs={TABS} value={tab} onChange={setTab} />
          <Card
            title={tab === "虚拟机" ? `虚拟机 · ${instances.length} 台` : tab}
            flush={tab === "虚拟机"}
          >
            {tab === "虚拟机" ? (
              instances.length ? (
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>名称</th>
                        <th>状态</th>
                        <th className="num">vCPU</th>
                        <th className="num">内存</th>
                        <th className="num">系统盘</th>
                        <th>镜像</th>
                      </tr>
                    </thead>
                    <tbody>
                      {instances.map((v) => (
                        <tr key={v.id}>
                          <td>
                            <button
                              className="text-link"
                              onClick={() => navigate("/admin/vms/" + v.id)}
                            >
                              {v.name}
                            </button>
                          </td>
                          <td>
                            <StatusBadge status={v.observed_state} />
                          </td>
                          <td className="num">{v.vcpu}</td>
                          <td className="num">{v.memory_mib / 1024} GB</td>
                          <td className="num">{v.disk_gib} GB</td>
                          <td className="muted">{v.image_name}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState icon="vm" title="该节点上暂无虚拟机" />
              )
            ) : tab === "概览" || tab === "代理与诊断" ? (
              <DescList
                columns={3}
                items={[
                  ["节点名称", node.name],
                  ["Agent 地址", <span className="mono">{node.endpoint}</span>],
                  ["Agent 版本", node.agent_version || "—"],
                  ["状态", <StatusBadge status={node.status} />],
                  ["可调度", node.is_schedulable ? "是" : "否"],
                  ["最近心跳", formatTime(node.last_seen_at)],
                  ["采样时间", formatTime(node.resource_sampled_at)],
                  ["采集周期", `${node.heartbeat_interval_seconds} 秒`],
                  ["离线阈值", `${node.offline_after_seconds} 秒`],
                  ["连续失败", `${node.consecutive_failures} 次`],
                  ["维护说明", node.maintenance_note || "—"],
                  [
                    "最近错误",
                    node.last_error_message ? (
                      <span className="danger-text">
                        {node.last_error_code} {node.last_error_message}
                      </span>
                    ) : (
                      "无"
                    ),
                  ],
                  ["注册时间", formatTime(node.created_at)],
                ]}
              />
            ) : (
              <EmptyState
                icon={tab === "监控" ? "trend" : tab === "网络" ? "network" : "storage"}
                title={`暂无节点级${tab}明细`}
                description={`当前尚未提供节点级${tab}明细 API`}
              />
            )}
          </Card>
        </>
      ) : !error ? (
        <div className="card">
          <LoadingState text="正在加载…" />
        </div>
      ) : null}
    </>
  );
}
