import type { ReactNode } from "react";

import { ApiError } from "../api";

export function formatBytes(value: number | null | undefined): string {
  if (!value || value <= 0) return "-";
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
  const tone = ["ONLINE", "RUNNING", "READY", "SUCCEEDED", "可用", "公开", "默认"].includes(normalized)
    ? "ok"
    : ["OFFLINE", "FAILED", "CRASHED", "CANCELLED", "禁用"].includes(normalized)
      ? "bad"
      : ["DEGRADED", "PENDING", "CREATING", "VALIDATING", "PREPARING", "RECONCILING", "管理网"].includes(
            normalized,
          )
        ? "warn"
        : "muted";
  return <span className={`badge badge-${tone}`}>{status || "UNKNOWN"}</span>;
}

export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="banner banner-error">{message}</div>;
}

export function Card({ title, extra, children }: { title: string; extra?: ReactNode; children: ReactNode }) {
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
