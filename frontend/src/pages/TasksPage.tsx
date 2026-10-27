import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBanner, StatusBadge, describeError, formatTime } from "../components/ui";
import { can } from "../permissions";
import type { CurrentUser, Task } from "../types";

export function TasksPage({ user }: { user: CurrentUser }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selected, setSelected] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const canCancel = can(user, "tasks.cancel_task");
  const canRetry = can(user, "tasks.retry_task");

  const reload = useCallback(async () => {
    try {
      setTasks((await api.tasks()).results);
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function open(task: Task) {
    try {
      setSelected(await api.task(task.id));
    } catch (err) {
      setError(describeError(err));
    }
  }

  async function cancel(task: Task) {
    if (!window.confirm(`确认取消任务 ${task.id.slice(0, 8)}？`)) return;
    setError(null);
    setNotice(null);
    try {
      await api.cancelTask(task.id);
      setNotice(`任务 ${task.id.slice(0, 8)} 已取消`);
      await reload();
      if (selected?.id === task.id) await open(task);
    } catch (err) {
      setError(describeError(err));
    }
  }

  async function retry(task: Task) {
    setError(null);
    setNotice(null);
    try {
      await api.retryTask(task.id);
      setNotice(`任务 ${task.id.slice(0, 8)} 已重新排队`);
      await reload();
      if (selected?.id === task.id) await open(task);
    } catch (err) {
      setError(describeError(err));
    }
  }

  return (
    <>
      <div className="page-head">
        <h2>任务</h2>
        <button className="action" onClick={() => void reload()}>刷新</button>
      </div>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      <Card title={`共 ${tasks.length} 个任务`}>
        {tasks.length === 0 ? <Empty text="暂无任务" /> : (
          <table>
            <thead>
              <tr>
                <th>任务</th>
                <th>类型</th>
                <th>状态</th>
                <th>资源</th>
                <th>尝试</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.id}>
                  <td className="mono">{task.id.slice(0, 8)}</td>
                  <td>{task.type}</td>
                  <td>
                    <StatusBadge status={task.status} />
                    {task.last_error_code ? <div className="muted">{task.last_error_code}</div> : null}
                  </td>
                  <td>{task.resource_type}:{task.resource_id}</td>
                  <td>{task.attempt_count}/{task.max_attempts}</td>
                  <td>{formatTime(task.created_at)}</td>
                  <td className="actions">
                    <button className="action" onClick={() => void open(task)}>详情</button>
                    {canCancel && task.status === "PENDING" ? (
                      <button className="action danger" onClick={() => void cancel(task)}>取消</button>
                    ) : null}
                    {canRetry && task.status === "FAILED" ? (
                      <button className="action" onClick={() => void retry(task)}>重试</button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {selected ? (
        <Card title={`任务详情 ${selected.id.slice(0, 8)}`}>
          <p className="muted">
            状态：{selected.status} / 尝试 {selected.attempt_count}/{selected.max_attempts}<br />
            创建：{formatTime(selected.created_at)} / 开始：{formatTime(selected.started_at)} / 完成：{formatTime(selected.finished_at)}
          </p>
          {selected.last_error_message ? <div className="banner banner-error">{selected.last_error_message}</div> : null}
          <div className="detail-panel">
            <h3>请求快照</h3>
            <pre className="json">{JSON.stringify(selected.payload ?? {}, null, 2)}</pre>
            <h3>执行结果</h3>
            <pre className="json">{JSON.stringify(selected.result ?? {}, null, 2)}</pre>
          </div>
          <h3>事件</h3>
          {(selected.events ?? []).length === 0 ? <Empty text="暂无事件" /> : (
            <table>
              <thead><tr><th>时间</th><th>尝试</th><th>迁移</th><th>级别</th><th>说明</th></tr></thead>
              <tbody>
                {(selected.events ?? []).map((event) => (
                  <tr key={event.id}>
                    <td>{formatTime(event.created_at)}</td>
                    <td>{event.attempt}</td>
                    <td className="mono">{event.from_status || "-"} → {event.to_status || "-"}</td>
                    <td>{event.level}</td>
                    <td>{event.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <button className="action" onClick={() => setSelected(null)}>关闭</button>
        </Card>
      ) : null}
    </>
  );
}
