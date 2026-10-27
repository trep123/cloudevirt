import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBanner, StatusBadge, describeError, formatTime } from "../components/ui";
import type { Task } from "../types";

export function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selected, setSelected] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <>
      <div className="page-head">
        <h2>任务</h2>
        <button className="action" onClick={() => void reload()}>刷新</button>
      </div>
      <ErrorBanner message={error} />
      <Card title={`共 ${tasks.length} 个任务`}>
        {tasks.length === 0 ? (
          <Empty text="暂无任务" />
        ) : (
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
                  <td>
                    {task.resource_type}:{task.resource_id}
                  </td>
                  <td>
                    {task.attempt_count}/{task.max_attempts}
                  </td>
                  <td>{formatTime(task.created_at)}</td>
                  <td>
                    <button className="action" onClick={() => void open(task)}>详情</button>
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
            状态：{selected.status} / 尝试 {selected.attempt_count} 次
          </p>
          {selected.last_error_message ? (
            <div className="banner banner-error">{selected.last_error_message}</div>
          ) : null}
          <h3>事件</h3>
          <table>
            <thead>
              <tr>
                <th>时间</th>
                <th>尝试</th>
                <th>迁移</th>
                <th>级别</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              {(selected.events ?? []).map((event) => (
                <tr key={event.id}>
                  <td>{formatTime(event.created_at)}</td>
                  <td>{event.attempt}</td>
                  <td className="mono">
                    {event.from_status || "-"} → {event.to_status || "-"}
                  </td>
                  <td>{event.level}</td>
                  <td>{event.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : null}
    </>
  );
}
