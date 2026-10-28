import type { ReactNode } from "react";

import { ApiError } from "../api";
import { Icon } from "./icons";

export function formatBytes(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value) || value < 0) return "—";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

const pad = (n: number) => String(n).padStart(2, "0");

/** 固定宽度的时间格式：YYYY-MM-DD HH:mm:ss，便于表格列对齐。 */
export function formatTimeFixed(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** 相对时间：刚刚 / 5 分钟前 / 3 小时前 / 2 天前。 */
export function formatRelative(value: string | null | undefined): string {
  if (!value) return "";
  const t = new Date(value).getTime();
  if (Number.isNaN(t)) return "";
  const diff = Math.round((Date.now() - t) / 1000);
  if (diff < 45) return "刚刚";
  if (diff < 3600) return `${Math.round(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.round(diff / 3600)} 小时前`;
  if (diff < 86400 * 30) return `${Math.round(diff / 86400)} 天前`;
  return formatTimeFixed(value).slice(0, 10);
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    const trace = error.requestId ? `（request_id: ${error.requestId}）` : "";
    return `${error.message} [${error.code}]${trace}`;
  }
  if (error instanceof Error) return error.message;
  return "未知错误";
}

const TONES: Record<string, string[]> = {
  ok: ["ONLINE", "RUNNING", "READY", "SUCCEEDED", "SUCCESS", "RESOLVED", "可用", "公开", "默认", "成功"],
  info: ["VALIDATING", "PREPARING", "CREATING", "VERIFYING", "RECONCILING", "MAINTENANCE", "INFO", "IMPORTING", "UPLOADING"],
  warn: ["DEGRADED", "PENDING", "PAUSED", "WARNING", "WARN", "DENIED", "管理网", "警告"],
  bad: ["OFFLINE", "FAILED", "FAILURE", "CRASHED", "CRITICAL", "ERROR", "禁用", "失败"],
};

/** 状态 → 语义色调：ok 绿 / info 蓝 / warn 琥珀 / bad 红 / muted 灰。 */
export function statusTone(status: string): "ok" | "info" | "warn" | "bad" | "muted" {
  const normalized = (status || "UNKNOWN").toUpperCase();
  for (const tone of ["ok", "info", "warn", "bad"] as const)
    if (TONES[tone].includes(normalized)) return tone;
  return "muted";
}

const STATUS_LABELS: Record<string, string> = {
  RUNNING: "运行中",
  SHUTOFF: "已关闭",
  STOPPED: "已停止",
  PAUSED: "已暂停",
  CRASHED: "异常",
  ONLINE: "在线",
  OFFLINE: "离线",
  UNKNOWN: "未知",
  PENDING: "等待执行",
  VALIDATING: "校验中",
  PREPARING: "准备中",
  CREATING: "创建中",
  VERIFYING: "验证中",
  RECONCILING: "对账中",
  SUCCEEDED: "成功",
  SUCCESS: "成功",
  FAILED: "失败",
  FAILURE: "失败",
  DENIED: "已拒绝",
  CANCELLED: "已取消",
  READY: "就绪",
  MAINTENANCE: "维护中",
  DEGRADED: "降级",
  WARNING: "警告",
  CRITICAL: "严重",
  ERROR: "错误",
  INFO: "信息",
  RESOLVED: "已恢复",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[(status || "UNKNOWN").toUpperCase()] || status || "未知";
}

export function StatusBadge({ status }: { status: string }) {
  const normalized = (status || "UNKNOWN").toUpperCase();
  const tone = statusTone(status);
  return (
    <span className={`badge badge-${tone}`}>
      {STATUS_LABELS[normalized] || status || "未知"}
    </span>
  );
}

export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div role="alert" className="banner banner-error">
      {message}
    </div>
  );
}

export function Card({
  title,
  description,
  extra,
  children,
  flush,
  className,
  footer,
}: {
  title?: ReactNode;
  description?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  /** 内容区不留内边距（表格卡片）。 */
  flush?: boolean;
  className?: string;
  footer?: ReactNode;
}) {
  return (
    <section
      className={
        "card" + (flush ? " card-flush" : "") + (className ? " " + className : "")
      }
    >
      {title || extra ? (
        <header className="card-head">
          <div className="card-title">
            {title ? <h2>{title}</h2> : null}
            {description ? <p>{description}</p> : null}
          </div>
          {extra ? <div className="card-extra">{extra}</div> : null}
        </header>
      ) : null}
      {flush ? <div className="card-body-flush">{children}</div> : children}
      {footer ? <footer className="card-foot">{footer}</footer> : null}
    </section>
  );
}

export function Empty({ text }: { text: string }) {
  return <p className="empty">{text}</p>;
}

/** 表格/列表的空状态：图标 + 标题 + 说明 + 可选操作。 */
export function EmptyState({
  title,
  description,
  icon = "inbox",
  action,
}: {
  title: string;
  description?: ReactNode;
  icon?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-state-icon">
        <Icon name={icon} size={22} />
      </span>
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
      {action}
    </div>
  );
}

export function LoadingState({ text = "正在加载…" }: { text?: string }) {
  return (
    <div className="loading-state" role="status">
      <span className="spinner" aria-hidden="true" />
      {text}
    </div>
  );
}

/** 页面级筛选工具栏（卡片）。左侧筛选项，右侧附加操作。 */
export function Toolbar({
  children,
  extra,
}: {
  children: ReactNode;
  extra?: ReactNode;
}) {
  return (
    <div className="toolbar">
      <div className="toolbar-filters">{children}</div>
      {extra ? <div className="toolbar-extra">{extra}</div> : null}
    </div>
  );
}

export function SearchInput({
  value,
  onChange,
  placeholder,
  label,
  width,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label?: string;
  width?: number;
}) {
  return (
    <label className="search-input" style={width ? { width } : undefined}>
      <Icon name="search" size={15} />
      <input
        type="search"
        aria-label={label || placeholder || "搜索"}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

/** 分段选择器，用于状态/类型快速筛选。 */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: ReactNode; count?: number }[];
  onChange: (value: T) => void;
  label?: string;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          type="button"
          role="radio"
          aria-checked={o.value === value}
          key={o.value}
          className={o.value === value ? "active" : ""}
          onClick={() => onChange(o.value)}
        >
          {o.label}
          {o.count != null ? <span className="segmented-count">{o.count}</span> : null}
        </button>
      ))}
    </div>
  );
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}

/** 列表分页页脚。 */
export function Pagination({
  page,
  pageSize,
  total,
  onChange,
  unit = "条",
}: {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
  unit?: string;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const nums: (number | "…")[] = [];
  for (let p = 1; p <= pages; p++) {
    if (p === 1 || p === pages || Math.abs(p - page) <= 1) nums.push(p);
    else if (nums[nums.length - 1] !== "…") nums.push("…");
  }
  return (
    <div className="pager">
      <span className="pager-info">
        共 {total} {unit} · 每页 {pageSize} {unit}
      </span>
      <div className="pager-nav">
        <button
          type="button"
          className="pager-btn"
          aria-label="上一页"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          <Icon name="chevronLeft" size={14} />
        </button>
        {nums.map((n, i) =>
          n === "…" ? (
            <span key={"e" + i} className="pager-gap">
              …
            </span>
          ) : (
            <button
              type="button"
              key={n}
              className={"pager-btn" + (n === page ? " active" : "")}
              aria-current={n === page ? "page" : undefined}
              onClick={() => onChange(n)}
            >
              {n}
            </button>
          ),
        )}
        <button
          type="button"
          className="pager-btn"
          aria-label="下一页"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
        >
          <Icon name="chevronRight" size={14} />
        </button>
      </div>
    </div>
  );
}

const AVATAR_HUES = [218, 160, 262, 28, 190, 330];
export function Avatar({ name, size = 24 }: { name: string; size?: number }) {
  const text = (name || "?").trim();
  let h = 0;
  for (const ch of text) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const hue = AVATAR_HUES[h % AVATAR_HUES.length];
  return (
    <span
      className="avatar"
      aria-hidden="true"
      style={{
        width: size,
        height: size,
        fontSize: Math.round(size * 0.46),
        background: `hsl(${hue} 70% 94%)`,
        color: `hsl(${hue} 55% 36%)`,
      }}
    >
      {text.slice(0, 1).toUpperCase()}
    </span>
  );
}

export function Tag({
  children,
  tone = "neutral",
  mono,
  title,
}: {
  children: ReactNode;
  tone?: "neutral" | "brand" | "ok" | "warn" | "bad" | "info";
  mono?: boolean;
  title?: string;
}) {
  return (
    <span className={`tag tag-${tone}${mono ? " mono" : ""}`} title={title}>
      {children}
    </span>
  );
}

/** 键值描述列表，按列数排成网格。 */
export function DescList({
  items,
  columns = 3,
}: {
  items: [ReactNode, ReactNode][];
  columns?: 1 | 2 | 3 | 4;
}) {
  return (
    <dl className={`desc-list desc-cols-${columns}`}>
      {items.map(([k, v], i) => (
        <div className="desc-item" key={i}>
          <dt>{k}</dt>
          <dd>{v === "" || v == null ? "—" : v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Tabs({
  tabs,
  value,
  onChange,
  label,
}: {
  tabs: string[];
  value: string;
  onChange: (value: string) => void;
  label?: string;
}) {
  return (
    <nav className="detail-tabs" aria-label={label} role="tablist">
      {tabs.map((t) => (
        <button
          key={t}
          role="tab"
          aria-selected={t === value}
          className={t === value ? "active" : ""}
          onClick={() => onChange(t)}
        >
          {t}
        </button>
      ))}
    </nav>
  );
}

/** 使用率进度条。 */
export function Meter({
  value,
  tone,
}: {
  value: number | null;
  tone?: "ok" | "warn" | "bad" | "brand";
}) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value));
  const t = tone || (pct >= 90 ? "bad" : pct >= 75 ? "warn" : "brand");
  return (
    <span className={`meter meter-${t}`} aria-hidden="true">
      <span style={{ width: pct + "%" }} />
    </span>
  );
}
