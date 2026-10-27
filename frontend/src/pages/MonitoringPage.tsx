import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBanner, StatusBadge, describeError, formatTime } from "../components/ui";
import type { Overview } from "../types";

export function MonitoringPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      setOverview(await api.overview());
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function reconcile() {
    setBusy(true);
    setNotice(null);
    try {
      const run = await api.runReconciliation();
      setNotice(`对账完成：${run.status}，差异 ${JSON.stringify(run.summary)}`);
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  const nodeTotal = Object.values(overview?.nodes ?? {}).reduce((sum, value) => sum + value, 0);
  const instanceTotal = Object.values(overview?.instances ?? {}).reduce((sum, value) => sum + value, 0);

  return (
    <>
      <div className="page-head">
        <h2>监控与对账</h2>
        <button className="action" disabled={busy} onClick={() => void reconcile()}>
          {busy ? "对账中…" : "立即对账"}
        </button>
      </div>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      <Card title="概览">
        <div className="stats">
          <div className="stat">
            <span>节点总数</span>
            <strong>{nodeTotal}</strong>
          </div>
          <div className="stat">
            <span>在线节点</span>
            <strong>{overview?.nodes.ONLINE ?? 0}</strong>
          </div>
          <div className="stat">
            <span>虚拟机总数</span>
            <strong>{instanceTotal}</strong>
          </div>
          <div className="stat">
            <span>运行中</span>
            <strong>{overview?.instances.RUNNING ?? 0}</strong>
          </div>
          <div className="stat">
            <span>活跃告警</span>
            <strong>{overview?.active_alerts.length ?? 0}</strong>
          </div>
        </div>
      </Card>
      <Card title="活跃告警">
        {(overview?.active_alerts.length ?? 0) === 0 ? (
          <Empty text="当前没有活跃告警" />
        ) : (
          <table>
            <thead>
              <tr>
                <th>级别</th>
                <th>类型</th>
                <th>对象</th>
                <th>说明</th>
                <th>最近出现</th>
              </tr>
            </thead>
            <tbody>
              {(overview?.active_alerts ?? []).map((alert) => (
                <tr key={alert.id}>
                  <td>
                    <StatusBadge status={alert.level} />
                  </td>
                  <td>{alert.type}</td>
                  <td className="mono">
                    {alert.resource_type}:{alert.resource_id}
                  </td>
                  <td>{alert.message}</td>
                  <td>{formatTime(alert.last_seen_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Card title="最近一次对账">
        {overview?.last_reconciliation.id ? (
          <p className="mono">
            状态 {overview.last_reconciliation.status} / 完成于{" "}
            {formatTime(overview.last_reconciliation.finished_at)}
            <br />
            {JSON.stringify(overview.last_reconciliation.summary)}
          </p>
        ) : (
          <Empty text="尚未执行过对账" />
        )}
      </Card>
    </>
  );
}
