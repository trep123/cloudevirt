import { useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { usePath, navigate } from "./app/router";
import { canEnterRoute } from "./app/permission";
import { AppLayout } from "./layouts/AppLayout";
import { OrganizationPage } from "./features/infrastructure/OrganizationPage";
import { StoragePoolsPage } from "./features/infrastructure/StoragePoolsPage";
import { SnapshotsPage } from "./features/infrastructure/SnapshotsPage";
import { SettingsPage } from "./features/infrastructure/SettingsPage";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { VmsPage } from "./features/vms/VmsPage";
import { VmConsolePage } from "./features/console/VmConsolePage";
import { StoragePage } from "./features/storage/StoragePage";
import { NodeDetailPage } from "./features/nodes/NodeDetailPage";
import { AuditPage } from "./features/audit/AuditPage";
import { UsersAndRolesPage } from "./features/users/UsersAndRolesPage";
import { ImagesPage } from "./pages/ImagesPage";
import { ChangePasswordGate, LoginPage } from "./pages/LoginPage";
import { MonitoringPage } from "./pages/MonitoringPage";
import { NetworksPage } from "./pages/NetworksPage";
import { NodesPage } from "./pages/NodesPage";
import { TasksPage } from "./pages/TasksPage";
import { TemplatesPage } from "./pages/TemplatesPage";
import { describeError, EmptyState } from "./components/ui";
import type { CurrentUser } from "./types";
export default function App() {
  const path = usePath(),
    [user, setUser] = useState<CurrentUser | null>(null),
    [booted, setBooted] = useState(false),
    [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch((e) => {
        if (!(e instanceof ApiError) || ![401, 403].includes(e.status))
          setError(describeError(e));
      })
      .finally(() => setBooted(true));
  }, []);
  const admin = user?.console_scope === "admin",
    prefix = admin ? "/admin" : "/app";
  useEffect(() => {
    if (user && ["/", "/login"].includes(path)) navigate(prefix + "/dashboard");
  }, [user, path, prefix]);
  useEffect(() => {
    const expired = () => {
      setUser(null);
      navigate("/login");
    };
    window.addEventListener("cloudvirt:session-expired", expired);
    return () =>
      window.removeEventListener("cloudvirt:session-expired", expired);
  }, []);
  async function logout() {
    try {
      await api.logout();
      setUser(null);
      navigate("/login");
    } catch (e) {
      setError(describeError(e));
    }
  }
  if (!booted)
    return (
      <div className="login-screen">
        <div className="login" role="status">
          <span
            className="auth-spinner auth-spinner-muted"
            aria-hidden="true"
          />
          正在连接 CloudVirt…
        </div>
      </div>
    );
  if (!user)
    return error ? (
      <div className="login-screen">
        <div className="login">
          <h1>暂时无法连接服务</h1>
          <p role="alert">{error}</p>
          <button className="action" onClick={() => location.reload()}>
            重新连接
          </button>
        </div>
      </div>
    ) : (
      <LoginPage onLogin={setUser} />
    );
  if (user.must_change_password)
    return (
      <ChangePasswordGate
        user={user}
        onDone={() => setUser({ ...user, must_change_password: false })}
        onLogout={() => void logout()}
      />
    );
  const key = path.split("/")[2] || "dashboard";
  const forbidden = !canEnterRoute(user, path);
  let content;
  if (forbidden || path === "/403")
    content = (
      <div className="card">
        <EmptyState
          icon="key"
          title="403 · 无权访问"
          description="当前账号没有此页面的访问权限。"
        />
      </div>
    );
  else if (path === "/404" || !path.startsWith(prefix + "/"))
    content = (
      <div className="card">
        <EmptyState icon="search" title="404 · 页面不存在" />
      </div>
    );
  else if (key === "dashboard") content = <DashboardPage admin={admin} />;
  else if ((key === "clusters" || key === "pools") && admin)
    content = <OrganizationPage key={key} kind={key} />;
  else if (key === "storage-pools" && admin) content = <StoragePoolsPage />;
  else if (key === "snapshots") content = <SnapshotsPage admin={admin} />;
  else if (key === "settings" && admin) content = <SettingsPage />;
  else if (/^\/(admin|app)\/vms\/\d+\/console$/.test(path))
    content = <VmConsolePage id={Number(path.split("/")[3])} admin={admin} />;
  else if (key === "vms") content = <VmsPage user={user} path={path} />;
  else if (key === "nodes" && admin)
    content = path.split("/")[3] ? (
      <NodeDetailPage id={Number(path.split("/")[3])} />
    ) : (
      <NodesPage user={user} />
    );
  else if (key === "images" && admin) content = <ImagesPage user={user} />;
  else if (key === "networks" && admin) content = <NetworksPage user={user} />;
  else if ((key === "users" || key === "roles") && admin)
    content = <UsersAndRolesPage user={user} />;
  else if (key === "audit") content = <AuditPage />;
  else if (key === "tasks") content = <TasksPage user={user} />;
  else if (key === "templates" && admin)
    content = <TemplatesPage user={user} />;
  else if (key === "storage" && admin) content = <StoragePage />;
  else if (key === "monitoring" && admin)
    content = <MonitoringPage user={user} />;
  else if (key === "profile")
    content = (
      <ChangePasswordGate
        user={user}
        onDone={() => navigate(prefix + "/dashboard")}
        onLogout={() => void logout()}
      />
    );
  else
    content = (
      <div className="card">
        <EmptyState
          icon="info"
          title="404 · 页面未开放"
          description="当前后端尚未提供此能力。"
          action={
            <button
              className="action"
              onClick={() => navigate(prefix + "/dashboard")}
            >
              返回工作台
            </button>
          }
        />
      </div>
    );
  return (
    <AppLayout
      user={user}
      admin={admin}
      path={path}
      onLogout={() => void logout()}
    >
      {error ? <p role="alert">{error}</p> : null}
      {content}
    </AppLayout>
  );
}
