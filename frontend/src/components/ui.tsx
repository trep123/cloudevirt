import type { ReactNode } from "react";

import { ApiError } from "../api";

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

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    const trace = error.requestId ? `（request_id: ${error.requestId}）` : "";
    return `${error.message} [${error.code}]${trace}`;
  }
  if (error instanceof Error) return error.message;
  return "未知错误";
}

export function StatusBadge({ status }: { status: string }) {
  const normalized = (status || "UNKNOWN").toUpperCase();
  const tone = [
    "ONLINE",
    "RUNNING",
    "READY",
    "SUCCEEDED",
    "可用",
    "公开",
    "默认",
  ].includes(normalized)
    ? "ok"
    : [
          "OFFLINE",
          "FAILED",
          "CRASHED",
          "CANCELLED",
          "CRITICAL",
          "禁用",
        ].includes(normalized)
      ? "bad"
      : [
            "DEGRADED",
            "PENDING",
            "CREATING",
            "VALIDATING",
            "PREPARING",
            "RECONCILING",
            "管理网",
          ].includes(normalized)
        ? "warn"
        : "muted";
  const labels: Record<string, string> = {
    RUNNING: "运行中",
    SHUTOFF: "已关闭",
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
    FAILED: "失败",
    CANCELLED: "已取消",
    READY: "就绪",
    MAINTENANCE: "维护中",
    DEGRADED: "降级",
    WARNING: "警告",
    CRITICAL: "严重",
  };
  return (
    <span className={`badge badge-${tone}`}>
      {labels[normalized] || status || "未知"}
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
  extra,
  children,
}: {
  title: string;
  extra?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card">
      <header className="card-head">
        <h2>{title}</h2>
        {extra}
      </header>
      {children}
    </section>
  );
}

export function Empty({ text }: { text: string }) {
  return <p className="empty">{text}</p>;
}
