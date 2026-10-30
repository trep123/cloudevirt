import type { CurrentUser } from "../types";

export function canEnterRoute(user: CurrentUser, path: string): boolean {
  if (path.startsWith("/admin") && user.console_scope !== "admin") return false;
  if (/\/vms\/\d+\/ssh$/.test(path) && !user.permissions.includes("instances.ssh_instance")) return false;
  const key = path.split("/")[2];
  if (
    ["clusters", "pools", "storage-pools", "settings"].includes(key) &&
    user.console_scope !== "admin"
  )
    return false;
  const required: Record<string, string> = {
    vms: "instances.view_instance",
    nodes: "nodes.view_node",
    images: "images.view_image",
    networks: "networks.view_network",
    tasks: "tasks.view_task",
    users: "accounts.manage_user",
    roles: "accounts.manage_role",
    templates: "templates.view_template",
    monitoring: "monitoring.view_alert",
    storage: "instances.view_instance",
    snapshots: "instances.view_instance",
  };
  if (
    path.endsWith("/vms/create") &&
    !user.permissions.includes("instances.add_instance")
  )
    return false;
  return !required[key] || user.permissions.includes(required[key]);
}
