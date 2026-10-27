/**
 * 统一 API 客户端。
 *
 * 约定：
 * - 同源 Session 认证，请求必须带 credentials；
 * - 写操作携带 X-CSRFToken（从 csrftoken Cookie 读取）；
 * - 错误统一抛 ApiError，保留后端 error.code / request_id 以便排查。
 */

import { type ApiErrorBody, type CurrentUser, type Paginated } from "./types";

const BASE = "/api/v1";

type PaginatedNodeAccess = { count: number; next: string | null; previous: string | null; results: import("./types").NodeAccess[] };

type NetworkInput = {
  name: string;
  type?: string;
  bridge?: string;
  vlan_id?: number | null;
  is_default?: boolean;
  is_management?: boolean;
  description?: string;
};

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
  request,
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
  createNode: (body: { name: string; endpoint: string }) =>
    request<import("./types").Node>("/nodes", { method: "POST", body: JSON.stringify(body) }),
  updateNode: (id: number, body: Partial<{ name: string; endpoint: string; status: string; maintenance_note: string; heartbeat_interval_seconds: number; offline_after_seconds: number }>) =>
    request<import("./types").Node>(`/nodes/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteNode: (id: number) => request<void>(`/nodes/${id}`, { method: "DELETE" }),
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
  updateImage: (id: number, body: Partial<{ os_family: string; os_version: string }>) =>
    request<import("./types").Image>(`/images/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteImage: (id: number, purgeFile = true) =>
    request<void>(`/images/${id}?purge_file=${purgeFile ? "true" : "false"}`, { method: "DELETE" }),
  disks: (filters: { status?: string; instance?: string } = {}) => {
    const params = new URLSearchParams({ page_size: "100" });
    if (filters.status) params.set("status", filters.status);
    if (filters.instance) params.set("instance", filters.instance);
    return request<Paginated<import("./types").Disk>>(`/disks?${params.toString()}`);
  },
  instances: () => request<Paginated<import("./types").Instance>>("/instances?page_size=100"),
  createInstance: (body: {
    name: string;
    node: number;
    image: number;
    vcpu: number;
    memory_mib: number;
    disk_gib: number;
    network_name?: string;
    autostart?: boolean;
  }) =>
    request<{ instance: import("./types").Instance; task: import("./types").TaskReference }>(
      "/instances",
      { method: "POST", body: JSON.stringify(body) },
    ),
  instanceAddresses: (id: number) =>
    request<{ addresses: import("./types").InstanceAddress[]; fetched_at: string }>(
      `/instances/${id}/addresses`,
    ),
  instanceInterfaces: (id: number) =>
    request<{ interfaces: import("./types").InstanceInterface[] }>(
      `/instances/${id}/interfaces`,
    ),
  instanceConsole: (id: number) =>
    request<{ type: string; path: string; password: string; expires_at: number }>(
      `/instances/${id}/console`,
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
  cancelTask: (id: string) => request<import("./types").Task>(`/tasks/${id}/cancel`, { method: "POST" }),
  retryTask: (id: string) => request<import("./types").Task>(`/tasks/${id}/retry`, { method: "POST" }),
  templates: () => request<Paginated<import("./types").Template>>("/templates?page_size=100"),
  createTemplate: (body: { name: string; vcpu: number; memory_mib: number; disk_gib: number; description?: string; is_public?: boolean }) =>
    request<import("./types").Template>("/templates", { method: "POST", body: JSON.stringify(body) }),
  updateTemplate: (id: number, body: Partial<{ name: string; vcpu: number; memory_mib: number; disk_gib: number; description: string; is_public: boolean }>) =>
    request<import("./types").Template>(`/templates/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteTemplate: (id: number) => request<void>(`/templates/${id}`, { method: "DELETE" }),
  users: () => request<Paginated<import("./types").User>>("/users?page_size=100"),
  createUser: (body: { username: string; email?: string; display_name?: string; password?: string; roles?: string[]; is_active?: boolean }) =>
    request<import("./types").User>("/users", { method: "POST", body: JSON.stringify(body) }),
  updateUser: (id: number, body: Partial<{ email: string; display_name: string; roles: string[]; is_active: boolean }>) =>
    request<import("./types").User>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteUser: (id: number) => request<void>(`/users/${id}`, { method: "DELETE" }),
  resetUserPassword: (id: number) =>
    request<{ username: string; password: string }>(`/users/${id}/reset-password`, { method: "POST" }),
  userAudit: (id: number) => request<{ results: import("./types").AuditEvent[] }>(`/users/${id}/audit`),
  nodeAccess: (nodeId?: number) =>
    request<PaginatedNodeAccess>("/node-access" + (nodeId ? "?node=" + nodeId : "")),
  createNodeAccess: (body: { node: number; user?: number; group?: number; permission: string }) =>
    request<import("./types").NodeAccess>("/node-access", { method: "POST", body: JSON.stringify(body) }),
  deleteNodeAccess: (id: number) => request<void>(`/node-access/${id}`, { method: "DELETE" }),
  networks: () => request<Paginated<import("./types").Network>>("/networks?page_size=100"),
  createNetwork: (body: NetworkInput) =>
    request<import("./types").Network>("/networks", { method: "POST", body: JSON.stringify(body) }),
  updateNetwork: (id: number, body: Partial<NetworkInput>) =>
    request<import("./types").Network>(`/networks/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteNetwork: (id: number) => request<void>(`/networks/${id}`, { method: "DELETE" }),
  overview: () => request<import("./types").Overview>("/monitoring/overview"),
  alerts: () => request<Paginated<import("./types").Alert>>("/monitoring/alerts?status=ACTIVE"),
  runReconciliation: () =>
    request<import("./types").ReconciliationRun>("/monitoring/reconciliation/run", {
      method: "POST",
    }),
  reconcileRuns: () =>
    request<Paginated<import("./types").ReconciliationRun>>("/monitoring/reconciliation?page_size=20"),
  reconcileRun: (id: number) =>
    request<import("./types").ReconciliationRun>(`/monitoring/reconciliation/${id}`),
};
