import { useEffect, useRef, type ReactNode } from "react";
import { api } from "../api";
import { describeError, StatusBadge } from "./ui";
import { useState } from "react";
import type { Task } from "../types";

export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <h2>{title}</h2>
        <p className="page-description">{description}</p>
      </div>
      <div className="actions">{children}</div>
    </div>
  );
}
export function ResourceStatCard({
  label,
  value,
  note,
}: {
  label: string;
  value: ReactNode;
  note: string;
}) {
  return (
    <div className="resource-stat">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}
export function ResourceUsageChart({
  range,
  onRange,
}: {
  range: string;
  onRange: (value: string) => void;
}) {
  return (
    <section className="card">
      <div className="card-head">
        <h2>集群资源趋势</h2>
        <select
          aria-label="趋势时间范围"
          value={range}
          onChange={(e) => onRange(e.target.value)}
        >
          {["1 小时", "24 小时", "7 天", "30 天"].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
      </div>
      <div className="chart-empty">
        <span className="chart-symbol">⌁</span>
        <strong>暂无时序数据</strong>
        <p>当前 Agent 尚未上报 CPU、磁盘 I/O 和网络趋势。</p>
        <p>时间范围：{range} · 接入指标采集后展示实际数据</p>
      </div>
    </section>
  );
}
export function Drawer({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = ref.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return (
    <dialog ref={ref} className="console-drawer" onCancel={onClose}>
      <header>
        <h2>{title}</h2>
        <button className="action" onClick={onClose} aria-label="关闭详情">
          关闭
        </button>
      </header>
      {children}
    </dialog>
  );
}
export function ConfirmOperationModal({
  target,
  operation,
  description,
  busy,
  error,
  onCancel,
  onConfirm,
}: {
  target: string;
  operation: string;
  description: string;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className="confirm-modal"
      onCancel={(e) => {
        if (busy) e.preventDefault();
        else onCancel();
      }}
    >
      <h2>{operation}确认</h2>
      <p>{description}</p>
      <dl>
        <dt>目标资源</dt>
        <dd>{target}</dd>
        <dt>目标操作</dt>
        <dd>{operation}</dd>
      </dl>
      {error ? (
        <p role="alert" className="danger-text">
          {error}
        </p>
      ) : null}
      <footer>
        <button className="action" disabled={busy} onClick={onCancel}>
          取消
        </button>
        <button className="action danger" disabled={busy} onClick={onConfirm}>
          {busy ? "提交中…" : `确认${operation}`}
        </button>
      </footer>
    </dialog>
  );
}
export function TaskProgressDrawer({
  id,
  onClose,
}: {
  id: string;
  onClose: () => void;
}) {
  const [task, setTask] = useState<Task | null>(null),
    [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true,
      working = false,
      finished = false;
    const load = async () => {
      if (working || finished || document.hidden) return;
      working = true;
      try {
        const result = await api.task(id);
        finished = ["SUCCEEDED", "FAILED", "CANCELLED"].includes(result.status);
        if (alive) {
          setTask(result);
          setError(null);
        }
      } catch (e) {
        if (alive) setError(describeError(e));
      } finally {
        working = false;
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 4000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [id]);
  return (
    <Drawer title="任务进度" onClose={onClose}>
      <p className="mono">{id}</p>
      {error ? (
        <p role="alert">{error}。连接中断不代表任务失败，请查询后再操作。</p>
      ) : null}
      {task ? (
        <>
          <StatusBadge status={task.status} />
          <p>{task.last_error_message}</p>
          <ol className="task-events">
            {task.events?.map((event) => (
              <li key={event.id}>{event.message}</li>
            ))}
          </ol>
        </>
      ) : (
        <p role="status">正在读取任务状态…</p>
      )}
    </Drawer>
  );
}
