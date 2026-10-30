import { useEffect, useState } from "react";
import { api } from "../../api";
import {
  ResourceStatCard,
  ResourceUsageChart,
  PageHeader,
} from "../../components/ConsoleUI";
import {
  Card,
  EmptyState,
  ErrorBanner,
  LoadingState,
  Meter,
  StatusBadge,
  describeError,
  formatRelative,
  formatTime,
  formatTimeFixed,
  statusTone,
} from "../../components/ui";
import { Icon } from "../../components/icons";
import { navigate } from "../../app/router";
import type { Alert, Task } from "../../types";
type Dashboard = {
  scope: string;
  sampled_at: string;
  nodes: { total: number; online: number };
  instances: { total: number; running: number };
  cpu_percent: number | null;
  cpu_sampled_nodes: number;
  memory_percent: number | null;
  alerts: Alert[];
  tasks: Task[];
};
export function DashboardPage({ admin }: { admin: boolean }) {
  const [data, setData] = useState<Dashboard | null>(null),
    [error, setError] = useState<string | null>(null),
    [range, setRange] = useState("1 小时");
  useEffect(() => {
    let alive = true,
      working = false;
    const load = async () => {
      if (working || document.hidden) return;
      working = true;
      try {
        const d = await api.request<Dashboard>("/console/dashboard");
        if (alive) {
          setData(d);
          setError(null);
        }
      } catch (e) {
        if (alive) setError(describeError(e));
      } finally {
        working = false;
      }
    };
    void load();
    const timer = setInterval(() => void load(), 15000);
    document.addEventListener("visibilitychange", load);
    return () => {
      alive = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", load);
    };
  }, []);
  const pct = (a: number, b: number) => (b ? Math.round((a / b) * 100) : 0);
  const tasksPath = admin ? "/admin/tasks" : "/app/tasks";
  return (
    <>
      <PageHeader
        title={admin ? "集群总览" : "我的工作台"}
        description={
          data
            ? `资源状态、告警与最近任务 · 数据更新于 ${formatTime(data.sampled_at)}`
            : "查看资源状态、采集结果及最近任务"
        }
      >
        {admin ? (
          <button className="action" onClick={() => navigate("/admin/monitoring")}>
            <Icon name="monitor" size={15} />
            监控与对账
          </button>
        ) : null}
        <button
          className="action"
          onClick={() => navigate((admin ? "/admin" : "/app") + "/vms")}
        >
          <Icon name="vm" size={15} />
          {admin ? "虚拟机列表" : "我的虚拟机"}
        </button>
      </PageHeader>
      <ErrorBanner message={error} />
      {!data ? (
        <div className="card">
          <LoadingState
            text={error ? "暂时无法读取总览" : "正在加载资源状态…"}
          />
        </div>
      ) : (
        <>
          <div className="resource-stats">
            <ResourceStatCard
              label={admin ? "物理节点" : "可用节点"}
              icon="server"
              tone={data.nodes.online < data.nodes.total ? "warn" : "ok"}
              value={
                <>
                  {data.nodes.online}
                  <span className="stat-unit"> / {data.nodes.total}</span>
                </>
              }
              note={`在线率 ${pct(data.nodes.online, data.nodes.total)}% · ${data.nodes.total - data.nodes.online} 个未在线`}
            >
              <Meter
                value={pct(data.nodes.online, data.nodes.total)}
                tone={data.nodes.online < data.nodes.total ? "warn" : "ok"}
              />
            </ResourceStatCard>
            <ResourceStatCard
              label={admin ? "虚拟机" : "我的虚拟机"}
              icon="vm"
              value={
                <>
                  {data.instances.running}
                  <span className="stat-unit"> / {data.instances.total}</span>
                </>
              }
              note={`${data.instances.running} 运行中 · ${data.instances.total - data.instances.running} 其他状态`}
            >
              <Meter
                value={pct(data.instances.running, data.instances.total)}
                tone="ok"
              />
            </ResourceStatCard>
            <ResourceStatCard
              label="CPU 使用率"
              icon="cpu"
              value={
                data.cpu_percent === null ? (
                  "—"
                ) : (
                  <>
                    {data.cpu_percent}
                    <span className="stat-unit">%</span>
                  </>
                )
              }
              note={data.cpu_percent === null ? "暂无有效 CPU 采样" : `按逻辑核数加权 · ${data.cpu_sampled_nodes} 个节点`}
            >
              <Meter value={data.cpu_percent} />
            </ResourceStatCard>
            <ResourceStatCard
              label="内存使用率"
              icon="memory"
              value={
                data.memory_percent === null ? (
                  "—"
                ) : (
                  <>
                    {data.memory_percent}
                    <span className="stat-unit">%</span>
                  </>
                )
              }
              note="仅使用未过期的节点采样"
            >
              <Meter value={data.memory_percent} />
            </ResourceStatCard>
          </div>
          <div className="dashboard-grid">
            <ResourceUsageChart range={range} onRange={setRange}>
              <div className="usage-rows">
                {[
                  ["CPU", data.cpu_percent, "cpu"],
                  ["内存", data.memory_percent, "memory"],
                  [
                    "节点在线率",
                    pct(data.nodes.online, data.nodes.total),
                    "server",
                  ],
                  [
                    "虚拟机运行率",
                    pct(data.instances.running, data.instances.total),
                    "vm",
                  ],
                ].map(([label, value, icon]) => (
                  <div className="usage-row" key={label as string}>
                    <span className="usage-label">
                      <Icon name={icon as string} size={15} />
                      {label}
                    </span>
                    <Meter value={value as number | null} />
                    <span className="usage-value mono">
                      {value === null ? "—" : `${value}%`}
                    </span>
                  </div>
                ))}
              </div>
            </ResourceUsageChart>
            <Card
              title="告警与健康状态"
              description={`${data.alerts.length} 条活跃告警`}
              extra={
                admin ? (
                  <button
                    className="action ghost sm"
                    onClick={() => navigate("/admin/monitoring")}
                  >
                    全部
                    <Icon name="chevronRight" size={14} />
                  </button>
                ) : null
              }
              className="alerts-card"
            >
              {data.alerts.length ? (
                <ul className="alert-list">
                  {data.alerts.map((a) => (
                    <li className={`alert-item alert-${statusTone(a.level)}`} key={a.id}>
                      <span className="alert-icon">
                        <Icon name="alert" size={15} />
                      </span>
                      <div className="alert-body">
                        <span className="alert-msg">{a.message}</span>
                        <span className="alert-meta">
                          <StatusBadge status={a.level} />
                          {a.last_seen_at ? (
                            <small className="muted">
                              {formatRelative(a.last_seen_at)}
                            </small>
                          ) : null}
                          {a.count > 1 ? (
                            <small className="muted">累计 {a.count} 次</small>
                          ) : null}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  icon="check"
                  title="当前范围暂无活跃告警"
                  description="采集状态以资源页面的最后观测时间为准。"
                />
              )}
            </Card>
          </div>
          <Card
            flush
            title="最近任务"
            description="最近提交的异步任务及执行状态"
            extra={
              <button
                className="action ghost sm"
                onClick={() => navigate(tasksPath)}
              >
                查看全部任务
                <Icon name="chevronRight" size={14} />
              </button>
            }
          >
            {data.tasks.length ? (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>任务类型</th>
                      <th>任务 ID</th>
                      <th>资源</th>
                      <th>状态</th>
                      <th>提交时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.tasks.map((t) => (
                      <tr key={t.id}>
                        <td>
                          <span className="strong">{t.type}</span>
                        </td>
                        <td className="mono muted">{t.id.slice(0, 8)}</td>
                        <td>
                          <span className="mono">
                            {t.resource_type}:{t.resource_id}
                          </span>
                        </td>
                        <td>
                          <StatusBadge status={t.status} />
                        </td>
                        <td>
                          <span className="mono time-text">
                            {formatTimeFixed(t.created_at)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState title="暂无任务记录" icon="task" />
            )}
          </Card>
        </>
      )}
    </>
  );
}
