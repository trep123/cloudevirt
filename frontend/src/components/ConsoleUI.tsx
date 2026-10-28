import { useEffect, useRef, type ReactNode } from "react";
import { api } from "../api";
import { describeError, StatusBadge } from "./ui";
import { Icon } from "./icons";
import { useState } from "react";
import type { Task } from "../types";

export function PageHeader({
  title,
  description,
  children,
  back,
  meta,
}: {
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  /** 返回上级：{ label, onClick } */
  back?: { label: string; onClick: () => void };
  /** 标题右侧的状态等附加信息 */
  meta?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div className="page-head-main">
        {back ? (
          <button type="button" className="page-back" onClick={back.onClick}>
            <Icon name="arrowLeft" size={14} />
            {back.label}
          </button>
        ) : null}
        <div className="page-title-row">
          <h1 className="page-title">{title}</h1>
          {meta ? <div className="page-meta">{meta}</div> : null}
        </div>
        {description ? (
          <p className="page-description">{description}</p>
        ) : null}
      </div>
      {children ? <div className="actions page-actions">{children}</div> : null}
    </div>
  );
}
export function ResourceStatCard({
  label,
  value,
  note,
  icon,
  tone = "brand",
  children,
}: {
  label: string;
  value: ReactNode;
  note: ReactNode;
  icon?: string;
  tone?: "brand" | "ok" | "warn" | "bad" | "info";
  children?: ReactNode;
}) {
  return (
    <div className={`resource-stat stat-${tone}`}>
      <div className="resource-stat-top">
        <span className="resource-stat-label">{label}</span>
        {icon ? (
          <span className="resource-stat-icon">
            <Icon name={icon} size={16} />
          </span>
        ) : null}
      </div>
      <strong>{value}</strong>
      {children}
      <small>{note}</small>
    </div>
  );
}
export function ResourceUsageChart({
  range,
  onRange,
  children,
}: {
  range: string;
  onRange: (value: string) => void;
  children?: ReactNode;
}) {
  return (
    <section className="card usage-card">
      <header className="card-head">
        <div className="card-title">
          <h2>集群资源使用</h2>
          <p>基于最近一次有效采样</p>
        </div>
        <div className="card-extra">
          <select
            aria-label="趋势时间范围"
            className="select-sm"
            value={range}
            onChange={(e) => onRange(e.target.value)}
          >
            {["1 小时", "24 小时", "7 天", "30 天"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </div>
      </header>
      {children}
      <div className="chart-empty chart-empty-compact">
        <Icon name="trend" size={18} />
        <div>
          <strong>暂无时序数据</strong>
          <p>
            当前 Agent 尚未上报 CPU、磁盘 I/O 和网络趋势 · 时间范围：{range}
          </p>
        </div>
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
        <button
          className="icon-btn"
          onClick={onClose}
          aria-label="关闭详情"
          title="关闭"
        >
          <Icon name="close" size={16} />
        </button>
      </header>
      <div className="console-drawer-body">{children}</div>
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
      <div className="confirm-head">
        <span className="confirm-icon">
          <Icon name="alert" size={18} />
        </span>
        <div>
          <h2>{operation}确认</h2>
          <p>{description}</p>
        </div>
      </div>
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
