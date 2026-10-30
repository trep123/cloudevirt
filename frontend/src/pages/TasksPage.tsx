import { useCallback, useEffect, useState, useRef } from "react";

import { api } from "../api";
import {
  Card,
  Pagination,
  DescList,
  Empty,
  EmptyState,
  ErrorBanner,
  Segmented,
  StatusBadge,
  Tag,
  Toolbar,
  describeError,
  formatTime,
  formatTimeFixed,
  statusTone,
} from "../components/ui";
import { Drawer, PageHeader } from "../components/ConsoleUI";
import { Icon } from "../components/icons";
import { can } from "../permissions";
import type { CurrentUser, Task } from "../types";

export function TasksPage({ user }: { user: CurrentUser }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1), [total, setTotal] = useState(0);
  const generation = useRef(0);
  const [selected, setSelected] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const canCancel = can(user, "tasks.cancel_task");
  const canRetry = can(user, "tasks.retry_task");

  const reload = useCallback(async () => {
    const token = ++generation.current;
    try {
      const result = await api.tasks({ page, status: filter === "FAILED" ? "failed" : filter });
      if (generation.current === token) { setTasks(result.results); setTotal(result.count); setError(null); }
    } catch (err) {
      if (generation.current === token) setError(describeError(err));
    }
  }, [page, filter]);

  useEffect(() => {
    let working = false;
    const update = async () => {
      if (document.hidden || working) return;
      working = true;
      try { await reload(); } finally { working = false; }
    };
    void update();
    const timer = window.setInterval(() => void update(), 5000);
    document.addEventListener("visibilitychange", update);
    return () => { generation.current++; clearInterval(timer); document.removeEventListener("visibilitychange", update); };
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

  const visible = tasks;

  return (
    <>
      <PageHeader
        title="任务"
        description="异步任务的执行状态、重试次数与事件记录"
      >
        <button className="action" onClick={() => void reload()}>
          <Icon name="refresh" size={15} />
          刷新
        </button>
      </PageHeader>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      <Toolbar>
        <Segmented
          label="任务状态"
          value={filter}
          onChange={value => { setFilter(value); setPage(1); }}
          options={[
            { value: "", label: "全部" },
            { value: "active", label: "进行中" },
            { value: "SUCCEEDED", label: "成功" },
            { value: "FAILED", label: "失败 / 取消" },
          ]}
        />
      </Toolbar>
      <Card flush title="任务列表" description={`共 ${total} 个任务 · 自动刷新，隐藏页面暂停`}>
        {visible.length === 0 ? (
          <EmptyState icon="task" title="暂无任务" />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>任务 ID</th>
                  <th>类型</th>
                  <th>状态</th>
                  <th>资源</th>
                  <th className="num">尝试</th>
                  <th>创建时间</th>
                  <th className="col-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((task) => (
                  <tr key={task.id}>
                    <td className="mono">{task.id.slice(0, 8)}</td>
                    <td className="strong">{task.type}</td>
                    <td>
                      <div className="cell-stack">
                        <span>
                          <StatusBadge status={task.status} />
                        </span>
                        {task.last_error_code ? (
                          <small className="danger-text">{task.last_error_code}</small>
                        ) : null}
                      </div>
                    </td>
                    <td className="mono">
                      {task.resource_type}:{task.resource_id}
                    </td>
                    <td className="num">
                      {task.attempt_count}/{task.max_attempts}
                    </td>
                    <td className="mono time-text">{formatTimeFixed(task.created_at)}</td>
                    <td className="col-actions">
                      <div className="row-actions">
                        <button className="action sm" onClick={() => void open(task)}>
                          详情
                        </button>
                        {canCancel && task.status === "PENDING" ? (
                          <button
                            className="action sm danger"
                            onClick={() => void cancel(task)}
                          >
                            取消
                          </button>
                        ) : null}
                        {canRetry && task.status === "FAILED" ? (
                          <button className="action sm" onClick={() => void retry(task)}>
                            重试
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <Pagination page={page} pageSize={20} total={total} onChange={setPage} />
      {selected ? (
        <Drawer
          title={`任务详情 ${selected.id.slice(0, 8)}`}
          onClose={() => setSelected(null)}
        >
          <div className="drawer-hero">
            <StatusBadge status={selected.status} />
            <Tag>{selected.type}</Tag>
          </div>
          <DescList
            columns={1}
            items={[
              ["任务 ID", <span className="mono">{selected.id}</span>],
              ["资源", <span className="mono">{selected.resource_type}:{selected.resource_id}</span>],
              ["尝试次数", `${selected.attempt_count}/${selected.max_attempts}`],
              ["创建", formatTime(selected.created_at)],
              ["开始", formatTime(selected.started_at)],
              ["完成", formatTime(selected.finished_at)],
            ]}
          />
          {selected.last_error_message ? (
            <div className="banner banner-error" style={{ marginTop: 16 }}>
              {selected.last_error_message}
            </div>
          ) : null}
          <div className="drawer-section">
            <h3>请求快照</h3>
            <pre className="json">{JSON.stringify(selected.payload ?? {}, null, 2)}</pre>
          </div>
          <div className="drawer-section">
            <h3>执行结果</h3>
            <pre className="json">{JSON.stringify(selected.result ?? {}, null, 2)}</pre>
          </div>
          <div className="drawer-section">
            <h3>事件</h3>
            {(selected.events ?? []).length === 0 ? (
              <Empty text="暂无事件" />
            ) : (
              <ol className="event-timeline">
                {(selected.events ?? []).map((event) => (
                  <li key={event.id} className={`event-${statusTone(event.level)}`}>
                    <div className="event-head">
                      <span className="mono">
                        {event.from_status || "-"} → {event.to_status || "-"}
                      </span>
                      <small className="muted">
                        第 {event.attempt} 次 · {formatTime(event.created_at)}
                      </small>
                    </div>
                    <p>
                      <Tag>{event.level}</Tag> {event.message}
                    </p>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </Drawer>
      ) : null}
    </>
  );
}
