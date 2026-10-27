import { useEffect, useState } from "react";
import { api } from "../../api";
import { navigate } from "../../app/router";
import { PageHeader, ResourceStatCard } from "../../components/ConsoleUI";
import {
  Card,
  ErrorBanner,
  StatusBadge,
  describeError,
  formatBytes,
  formatTime,
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
  return (
    <>
      <PageHeader
        title={node?.name || "物理节点"}
        description={node ? node.endpoint : "读取节点信息"}
      >
        <button className="action" onClick={() => navigate("/admin/nodes")}>
          返回节点列表
        </button>
      </PageHeader>
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
              value={<StatusBadge status={node.status} />}
              note={node.agent_version || "Agent 版本未知"}
            />
            <ResourceStatCard
              label="逻辑 CPU"
              value={node.cpu_total ?? "—"}
              note="尚未采集 CPU 使用率"
            />
            <ResourceStatCard
              label="可用内存"
              value={
                node.memory_available_mib === null
                  ? "—"
                  : (node.memory_available_mib / 1024).toFixed(1) + " GB"
              }
              note={`总量 ${node.memory_total_mib === null ? "—" : (node.memory_total_mib / 1024).toFixed(1) + " GB"}`}
            />
            <ResourceStatCard
              label="剩余存储"
              value={formatBytes(node.storage_free_bytes)}
              note={`总量 ${formatBytes(node.storage_total_bytes)}`}
            />
          </div>
          <nav className="detail-tabs">
            {TABS.map((t) => (
              <button
                key={t}
                className={tab === t ? "active" : ""}
                onClick={() => setTab(t)}
              >
                {t}
              </button>
            ))}
          </nav>
          <Card title={tab}>
            {tab === "虚拟机" ? (
              <table>
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>状态</th>
                    <th>vCPU</th>
                    <th>内存</th>
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
                      <td>{v.vcpu}</td>
                      <td>{v.memory_mib / 1024} GB</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : tab === "概览" || tab === "代理与诊断" ? (
              <dl className="info-grid">
                <dt>Agent 版本</dt>
                <dd>{node.agent_version || "—"}</dd>
                <dt>最近心跳</dt>
                <dd>{formatTime(node.last_seen_at)}</dd>
                <dt>采样时间</dt>
                <dd>{formatTime(node.resource_sampled_at)}</dd>
                <dt>维护说明</dt>
                <dd>{node.maintenance_note || "—"}</dd>
                <dt>最近错误</dt>
                <dd>
                  {node.last_error_code} {node.last_error_message || "无"}
                </dd>
              </dl>
            ) : (
              <div className="chart-empty">当前尚未提供节点级{tab}明细 API</div>
            )}
          </Card>
        </>
      ) : !error ? (
        <p role="status">正在加载…</p>
      ) : null}
    </>
  );
}
