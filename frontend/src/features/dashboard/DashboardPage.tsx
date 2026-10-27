import { useEffect, useState } from "react";
import { api } from "../../api";
import {
  ResourceStatCard,
  ResourceUsageChart,
  PageHeader,
} from "../../components/ConsoleUI";
import {
  Card,
  ErrorBanner,
  StatusBadge,
  formatTime,
  describeError,
} from "../../components/ui";
import { navigate } from "../../app/router";
import type { Alert, Task } from "../../types";
type Dashboard = {
  scope: string;
  sampled_at: string;
  nodes: { total: number; online: number };
  instances: { total: number; running: number };
  cpu_percent: number | null;
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
  return (
    <>
      <PageHeader
        title={admin ? "集群总览" : "我的工作台"}
        description="查看资源状态、采集结果及最近任务"
      />
      <ErrorBanner message={error} />
      {!data ? (
        <div className="card" role="status">
          {error ? "暂时无法读取总览" : "正在加载资源状态…"}
        </div>
      ) : (
        <>
          <div className="resource-stats">
            <ResourceStatCard
              label={admin ? "物理节点" : "可用节点"}
              value={`${data.nodes.online} / ${data.nodes.total}`}
              note="在线 / 授权节点"
            />
            <ResourceStatCard
              label={admin ? "虚拟机" : "我的虚拟机"}
              value={data.instances.total}
              note={`${data.instances.running} 运行 · ${data.instances.total - data.instances.running} 其他状态`}
            />
            <ResourceStatCard
              label="CPU 使用率"
              value={data.cpu_percent === null ? "—" : `${data.cpu_percent}%`}
              note="尚未采集 CPU 指标"
            />
            <ResourceStatCard
              label="内存使用率"
              value={
                data.memory_percent === null ? "—" : `${data.memory_percent}%`
              }
              note="仅使用未过期的节点采样"
            />
          </div>
          <div className="dashboard-grid">
            <ResourceUsageChart range={range} onRange={setRange} />
            <Card title="告警与健康状态">
              <p className="muted">聚合更新：{formatTime(data.sampled_at)}</p>
              {data.alerts.length ? (
                data.alerts.map((a) => (
                  <div className="health-row" key={a.id}>
                    <StatusBadge status={a.level} />
                    <span>{a.message}</span>
                  </div>
                ))
              ) : (
                <div className="health-empty">
                  当前范围暂无活跃告警
                  <p className="muted">
                    采集状态以资源页面的最后观测时间为准。
                  </p>
                </div>
              )}
            </Card>
          </div>
          <Card
            title="最近任务"
            extra={
              <button
                className="action"
                onClick={() => navigate(admin ? "/admin/tasks" : "/app/tasks")}
              >
                查看全部任务 →
              </button>
            }
          >
            <table>
              <thead>
                <tr>
                  <th>任务</th>
                  <th>资源</th>
                  <th>状态</th>
                  <th>提交时间</th>
                </tr>
              </thead>
              <tbody>
                {data.tasks.map((t) => (
                  <tr key={t.id}>
                    <td>{t.type}</td>
                    <td className="mono">
                      {t.resource_type}:{t.resource_id}
                    </td>
                    <td>
                      <StatusBadge status={t.status} />
                    </td>
                    <td>{formatTime(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.tasks.length ? <p className="empty">暂无任务记录</p> : null}
          </Card>
        </>
      )}
    </>
  );
}
