import { api } from "../../api";
import type { Paginated } from "../../types";

export type Cluster = {
  id: number;
  name: string;
  description: string;
  node_ids: number[];
  nodes: {
    id: number;
    name: string;
    status: string;
    resource_is_stale: boolean;
    last_seen_at: string | null;
  }[];
  instances: number;
  usage: Usage;
};
export type Usage = { vcpu: number; memory_mib: number; disk_gib: number };
export type Pool = {
  id: number;
  name: string;
  description: string;
  cluster_id: number;
  cluster_name: string;
  vcpu_limit: number;
  memory_mib_limit: number;
  disk_gib_limit: number;
  instance_ids: number[];
  usage: Usage;
};
export type Configuration = {
  revision: number;
  quota: Usage & { instances: number };
  storage_warning_percent: number;
  storage_critical_percent: number;
};
export async function allResources<T>(path: string): Promise<T[]> {
  const rows: T[] = [];
  let page = 1;
  while (true) {
    const result = await api.request<Paginated<T>>(
      `${path}${path.includes("?") ? "&" : "?"}page_size=100&page=${page}`,
    );
    rows.push(...result.results);
    if (!result.next) return rows;
    page++;
  }
}
export const infra = {
  clusters: () => api.request<{ results: Cluster[] }>("/admin/clusters/"),
  pools: () => api.request<{ results: Pool[] }>("/admin/resource-pools/"),
  configuration: () => api.request<Configuration>("/admin/settings/"),
  save: (path: string, body: unknown, key?: string) =>
    api.request<{ task_id: string }>(path, {
      method: "POST",
      headers: key ? { "Idempotency-Key": key } : {},
      body: JSON.stringify(body),
    }),
};
