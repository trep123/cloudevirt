import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import { ImagesPage } from "./pages/ImagesPage";
import { InstancesPage } from "./pages/InstancesPage";
import { ChangePasswordGate, LoginPage } from "./pages/LoginPage";
import { MonitoringPage } from "./pages/MonitoringPage";
import { NetworksPage } from "./pages/NetworksPage";
import { NodesPage } from "./pages/NodesPage";
import { TasksPage } from "./pages/TasksPage";
import { UsersPage } from "./pages/UsersPage";
import type { CurrentUser } from "./types";

type PageKey = "instances" | "nodes" | "images" | "networks" | "tasks" | "monitoring" | "users";

const NAV: { key: PageKey; label: string; permission?: string }[] = [
  { key: "instances", label: "虚拟机" },
  { key: "nodes", label: "节点" },
  { key: "images", label: "镜像" },
  { key: "networks", label: "网络" },
  { key: "tasks", label: "任务" },
  { key: "monitoring", label: "监控" },
  { key: "users", label: "用户与权限", permission: "accounts.manage_user" },
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

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>CloudVirt</h1>
        {NAV.filter((item) => !item.permission || user.permissions.includes(item.permission)).map((item) => (
          <button
            key={item.key}
            className={page === item.key ? "active" : ""}
            onClick={() => setPage(item.key)}
          >
            {item.label}
          </button>
        ))}
        <div className="spacer" />
        <div className="who">
          {user.display_name || user.username}
          <br />
          {user.roles.join(" / ") || "无角色"}
        </div>
        <button onClick={() => void logout()}>退出登录</button>
      </aside>
      <main className="main">
        {page === "instances" ? <InstancesPage /> : null}
        {page === "nodes" ? <NodesPage /> : null}
        {page === "images" ? <ImagesPage /> : null}
        {page === "networks" ? <NetworksPage /> : null}
        {page === "tasks" ? <TasksPage /> : null}
        {page === "monitoring" ? <MonitoringPage /> : null}
        {page === "users" ? <UsersPage /> : null}
      </main>
    </div>
  );
}
