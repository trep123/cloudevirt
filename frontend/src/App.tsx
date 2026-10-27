import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import { DisksPage } from "./pages/DisksPage";
import { ImagesPage } from "./pages/ImagesPage";
import { InstancesPage } from "./pages/InstancesPage";
import { ChangePasswordGate, LoginPage } from "./pages/LoginPage";
import { MonitoringPage } from "./pages/MonitoringPage";
import { NetworksPage } from "./pages/NetworksPage";
import { NodesPage } from "./pages/NodesPage";
import { TasksPage } from "./pages/TasksPage";
import { TemplatesPage } from "./pages/TemplatesPage";
import { UsersPage } from "./pages/UsersPage";
import { roleLabel } from "./roles";
import type { CurrentUser } from "./types";

type PageKey =
  | "instances"
  | "nodes"
  | "images"
  | "templates"
  | "networks"
  | "disks"
  | "tasks"
  | "monitoring"
  | "users";

type NavItem = {
  key: PageKey;
  label: string;
  group: string;
  permission: string;
};

const GROUPS = ["资源", "运维", "管理"];

const NAV: NavItem[] = [
  { key: "instances", label: "虚拟机", group: "资源", permission: "instances.view_instance" },
  { key: "nodes", label: "节点", group: "资源", permission: "nodes.view_node" },
  { key: "images", label: "镜像", group: "资源", permission: "images.view_image" },
  { key: "templates", label: "模板", group: "资源", permission: "templates.view_template" },
  { key: "networks", label: "网络", group: "资源", permission: "networks.view_network" },
  { key: "disks", label: "磁盘", group: "资源", permission: "instances.view_instance" },
  { key: "tasks", label: "任务", group: "运维", permission: "tasks.view_task" },
  { key: "monitoring", label: "监控", group: "运维", permission: "monitoring.view_alert" },
  { key: "users", label: "用户与权限", group: "管理", permission: "accounts.manage_user" },
];

export default function App() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [booted, setBooted] = useState(false);
  const [page, setPage] = useState<PageKey>("instances");

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setBooted(true));
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }, []);

  if (!booted) {
    return <div className="main">加载中…</div>;
  }

  if (!user) {
    return <LoginPage onLogin={setUser} />;
  }

  if (user.must_change_password) {
    return (
      <ChangePasswordGate
        user={user}
        onDone={() => setUser({ ...user, must_change_password: false })}
        onLogout={() => void logout()}
      />
    );
  }

  const visibleNav = NAV.filter((item) => user.permissions.includes(item.permission));

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>CloudVirt</h1>
        {GROUPS.map((group) => {
          const items = visibleNav.filter((item) => item.group === group);
          if (items.length === 0) return null;
          return (
            <div className="nav-group" key={group}>
              <div className="nav-title">{group}</div>
              {items.map((item) => (
                <button
                  key={item.key}
                  className={page === item.key ? "active" : ""}
                  onClick={() => setPage(item.key)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          );
        })}
        <div className="spacer" />
        <div className="who">
          {user.display_name || user.username}
          <br />
          {user.roles.map(roleLabel).join(" / ") || "无角色"}
        </div>
        <button onClick={() => void logout()}>退出登录</button>
      </aside>
      <main className="main">
        {page === "instances" ? <InstancesPage user={user} /> : null}
        {page === "nodes" ? <NodesPage user={user} /> : null}
        {page === "images" ? <ImagesPage user={user} /> : null}
        {page === "templates" ? <TemplatesPage user={user} /> : null}
        {page === "networks" ? <NetworksPage user={user} /> : null}
        {page === "disks" ? <DisksPage /> : null}
        {page === "tasks" ? <TasksPage user={user} /> : null}
        {page === "monitoring" ? <MonitoringPage user={user} /> : null}
        {page === "users" ? <UsersPage /> : null}
      </main>
    </div>
  );
}
