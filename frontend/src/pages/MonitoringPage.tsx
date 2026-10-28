import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBanner, StatusBadge, describeError, formatTime } from "../components/ui";
import { PageHeader } from "../components/ConsoleUI";
import { can } from "../permissions";
import type { CurrentUser, Overview, ReconciliationRun } from "../types";

export function MonitoringPage({ user }: { user: CurrentUser }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [runs, setRuns] = useState<ReconciliationRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<ReconciliationRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canReconcile = can(user, "monitoring.run_reconciliation");

  const reload = useCallback(async () => {
    try {
      const [overviewData, runPage] = await Promise.all([api.overview(), api.reconcileRuns()]);
      setOverview(overviewData);
      setRuns(runPage.results);
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
    setError(null);
    try {
      const run = await api.runReconciliation();
      setNotice(`对账完成：${run.status}，差异 ${JSON.stringify(run.summary)}`);
      setSelectedRun(run);
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function openRun(run: ReconciliationRun) {
    try {
      setSelectedRun(await api.reconcileRun(run.id));
    } catch (err) {
      setError(describeError(err));
    }
  }

  const nodeTotal = Object.values(overview?.nodes ?? {}).reduce((sum, value) => sum + value, 0);
  const instanceTotal = Object.values(overview?.instances ?? {}).reduce((sum, value) => sum + value, 0);

  return (
    <>
      <PageHeader
        title="监控与对账"
        description="资源状态汇总、活跃告警与数据库 / 节点实际状态对账记录"
      >
        {canReconcile ? (
          <button className="action primary" disabled={busy} onClick={() => void reconcile()}>
            {busy ? "对账中…" : "立即对账"}
          </button>
        ) : null}
      </PageHeader>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      <Card title="概览">
        <div className="stats">
          <div className="stat"><span>节点总数</span><strong>{nodeTotal}</strong></div>
          <div className="stat"><span>在线节点</span><strong>{overview?.nodes.ONLINE ?? 0}</strong></div>
          <div className="stat"><span>虚拟机总数</span><strong>{instanceTotal}</strong></div>
          <div className="stat"><span>运行中</span><strong>{overview?.instances.RUNNING ?? 0}</strong></div>
          <div className="stat"><span>活跃告警</span><strong>{overview?.active_alerts.length ?? 0}</strong></div>
        </div>
      </Card>
      <Card title="活跃告警">
        {(overview?.active_alerts.length ?? 0) === 0 ? <Empty text="当前没有活跃告警" /> : (
          <div className="table-scroll">
          <table>
            <thead><tr><th>级别</th><th>类型</th><th>对象</th><th>说明</th><th>最近出现</th></tr></thead>
            <tbody>
              {(overview?.active_alerts ?? []).map((alert) => (
                <tr key={alert.id}>
                  <td><StatusBadge status={alert.level} /></td>
                  <td>{alert.type}</td>
                  <td className="mono">{alert.resource_type}:{alert.resource_id}</td>
                  <td>{alert.message}</td>
                  <td>{formatTime(alert.last_seen_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </Card>
      <Card title={`对账历史（最近 ${runs.length} 次）`}>
        {runs.length === 0 ? <Empty text="尚未执行过对账" /> : (
          <div className="table-scroll">
          <table>
            <thead><tr><th>批次</th><th>状态</th><th>开始</th><th>完成</th><th>摘要</th><th className="col-actions">操作</th></tr></thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>#{run.id}</td>
                  <td><StatusBadge status={run.status} /></td>
                  <td>{formatTime(run.started_at)}</td>
                  <td>{formatTime(run.finished_at)}</td>
                  <td className="mono muted"><span className="truncate cell-desc" title={JSON.stringify(run.summary)}>{JSON.stringify(run.summary)}</span></td>
                  <td className="actions"><button className="action" onClick={() => void openRun(run)}>查看差异</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </Card>
      {selectedRun ? (
        <Card title={`对账差异：批次 #${selectedRun.id}`}>
          <p className="muted">
            状态 {selectedRun.status} / 完成于 {formatTime(selectedRun.finished_at)}<br />
            摘要：<span className="mono">{JSON.stringify(selectedRun.summary)}</span>
          </p>
          {selectedRun.diffs.length === 0 ? <Empty text="本次对账没有差异" /> : (
            <div className="table-scroll">
            <table>
              <thead><tr><th>类型</th><th>对象</th><th>详情</th><th>处理方式</th><th>备注</th></tr></thead>
              <tbody>
                {selectedRun.diffs.map((diff) => (
                  <tr key={diff.id}>
                    <td>{diff.kind}</td>
                    <td className="mono">{diff.resource_type}:{diff.resource_id}</td>
                    <td className="mono muted">{JSON.stringify(diff.detail)}</td>
                    <td>{diff.resolution}</td>
                    <td>{diff.note || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
          <button className="action" onClick={() => setSelectedRun(null)}>关闭</button>
        </Card>
      ) : null}
    </>
  );
}
