/** 后端统一错误结构。 */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
    request_id: string;
  };
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export type NodeStatus = "UNKNOWN" | "ONLINE" | "DEGRADED" | "OFFLINE" | "MAINTENANCE";

export interface Node {
  id: number;
  name: string;
  endpoint: string;
  status: NodeStatus;
  agent_version: string;
  cpu_total: number | null;
  memory_total_mib: number | null;
  memory_available_mib: number | null;
  storage_total_bytes: number | null;
  storage_free_bytes: number | null;
  resource_sampled_at: string | null;
  resource_is_stale: boolean;
  last_seen_at: string | null;
  consecutive_failures: number;
  last_error_code: string;
  last_error_message: string;
  is_schedulable: boolean;
}

export interface Image {
  id: number;
  name: string;
  format: string;
  relative_path: string;
  size_bytes: number;
  virtual_size_bytes: number | null;
  status: string;
  os_family: string;
  os_version: string;
  error_code: string;
  error_message: string;
  is_ready: boolean;
}

export interface Network {
  id: number;
  name: string;
  type: string;
  bridge: string;
  vlan_id: number | null;
  is_default: boolean;
  is_management: boolean;
  description: string;
  is_usable: boolean;
}

export interface Disk {
  id: number;
  role: string;
  name: string;
  size_gib: number;
  status: string;
  target_dev: string;
}

export interface Instance {
  id: number;
  uuid: string;
  name: string;
  libvirt_domain_name: string;
  node: number;
  node_name: string;
  image: number;
  image_name: string;
  network_name: string;
  vcpu: number;
  memory_mib: number;
  disk_gib: number;
  desired_state: string;
  observed_state: string;
  observed_state_updated_at: string | null;
  observed_state_is_stale: boolean;
  operation_status: string;
  last_error_code: string;
  last_error_message: string;
  disks: Disk[];
}

export interface Task {
  id: string;
  type: string;
  status: string;
  resource_type: string;
  resource_id: string;
  attempt_count: number;
  max_attempts: number;
  last_error_code: string;
  created_at: string;
  updated_at: string;
  payload?: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  last_error_message?: string;
  events?: TaskEvent[];
}

export interface TaskEvent {
  id: number;
  attempt: number;
  from_status: string;
  to_status: string;
  level: string;
  error_code: string;
  message: string;
  created_at: string;
}

export interface Alert {
  id: number;
  type: string;
  level: string;
  status: string;
  message: string;
  resource_type: string;
  resource_id: string;
  count: number;
  first_seen_at: string;
  last_seen_at: string;
}

export interface Overview {
  nodes: Record<string, number>;
  instances: Record<string, number>;
  active_alerts: Alert[];
  last_reconciliation: {
    id: number | null;
    status: string | null;
    finished_at: string | null;
    summary: Record<string, number>;
  };
}

export interface CurrentUser {
  id: number;
  username: string;
  display_name: string;
  roles: string[];
  permissions: string[];
  must_change_password: boolean;
}

export interface TaskReference {
  id: string;
  status: string;
  status_url: string;
}
