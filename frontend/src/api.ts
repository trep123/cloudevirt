/**
 * 统一 API 客户端。
 *
 * 约定：
 * - 同源 Session 认证，请求必须带 credentials；
 * - 写操作携带 X-CSRFToken（从 csrftoken Cookie 读取）；
 * - 错误统一抛 ApiError，保留后端 error.code / request_id 以便排查。
 */

import type { ApiErrorBody, CurrentUser, Paginated } from "./types";

const BASE = "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody["error"] | null) {
    super(body?.message || `请求失败（HTTP ${status}）`);
    this.status = status;
    this.code = body?.code || "UNKNOWN";
    this.requestId = body?.request_id || "";
    this.details = body?.details || {};
  }
}

function readCookie(name: string): string {
  const target = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const item = part.trim();
    if (item.startsWith(target)) {
      return decodeURIComponent(item.slice(target.length));
    }
  }
  return "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const token = readCookie("csrftoken");
    if (token) {
      headers.set("X-CSRFToken", token);
    }
  }
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    method,
    headers,
    credentials: "same-origin",
  });
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new ApiError(response.status, (payload as ApiErrorBody)?.error ?? null);
  }
  return payload as T;
}

export const api = {
  me: () => request<CurrentUser>("/auth/me"),
  login: (username: string, password: string) =>
    request<CurrentUser>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  changePassword: (oldPassword: string, newPassword: string) =>
    request<{ ok: boolean }>("/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
    }),
  nodes: () => request<Paginated<import("./types").Node>>("/nodes?page_size=100"),
  refreshNode: (id: number) =>
    request<import("./types").Node>(`/nodes/${id}/refresh`, { method: "POST" }),
  images: () => request<Paginated<import("./types").Image>>("/images?page_size=100"),
  importImage: (body: {
    name: string;
    node: number;
    relative_path: string;
    os_family?: string;
    os_version?: string;
  }) => request<import("./types").Image>("/images", { method: "POST", body: JSON.stringify(body) }),
  deleteImage: (id: number) =>
    request<void>(`/images/${id}`, { method: "DELETE" }),
  instances: () => request<Paginated<import("./types").Instance>>("/instances?page_size=100"),
  createInstance: (body: {
    name: string;
    node: number;
    image: number;
    vcpu: number;
    memory_mib: number;
    disk_gib: number;
    network_name?: string;
  }) =>
    request<{ instance: import("./types").Instance; task: import("./types").TaskReference }>(
      "/instances",
      { method: "POST", body: JSON.stringify(body) },
    ),
  instanceAction: (id: number, action: string) =>
    request<{ task: import("./types").TaskReference | null }>(`/instances/${id}/${action}`, {
      method: "POST",
    }),
  deleteInstance: (id: number, purgeDisk: boolean) =>
    request<{ task: import("./types").TaskReference }>(
      `/instances/${id}?purge_disk=${purgeDisk ? "true" : "false"}`,
      { method: "DELETE" },
    ),
  tasks: () => request<Paginated<import("./types").Task>>("/tasks?page_size=50"),
  task: (id: string) => request<import("./types").Task>(`/tasks/${id}`),
  networks: () => request<Paginated<import("./types").Network>>("/networks?page_size=100"),
  overview: () => request<import("./types").Overview>("/monitoring/overview"),
  alerts: () => request<Paginated<import("./types").Alert>>("/monitoring/alerts?status=ACTIVE"),
  runReconciliation: () =>
    request<{ id: number; status: string; summary: Record<string, number> }>(
      "/monitoring/reconciliation/run",
      { method: "POST" },
    ),
};
