import { useState, type ReactNode } from "react";
import { navigate } from "../app/router";
import type { CurrentUser } from "../types";
type Item = {
  label: string;
  key: string;
  permission?: string;
  disabled?: boolean;
};
const groups: { label: string; key: string; items: Item[] }[] = [
  { label: "总览", key: "dashboard", items: [] },
  {
    label: "计算资源",
    key: "vms",
    items: [
      { label: "集群", key: "clusters", disabled: true },
      { label: "物理节点", key: "nodes", permission: "nodes.view_node" },
      { label: "虚拟机", key: "vms", permission: "instances.view_instance" },
      { label: "资源池", key: "pools", disabled: true },
      {
        label: "规格模板",
        key: "templates",
        permission: "templates.view_template",
      },
    ],
  },
  {
    label: "存储管理",
    key: "storage",
    items: [
      { label: "数据卷", key: "storage" },
      { label: "镜像", key: "images", permission: "images.view_image" },
      { label: "存储池 / 快照", key: "snapshots", disabled: true },
    ],
  },
  { label: "网络管理", key: "networks", items: [] },
  { label: "用户与权限", key: "users", items: [] },
  {
    label: "任务与审计",
    key: "tasks",
    items: [
      { label: "异步任务", key: "tasks" },
      {
        label: "监控与对账",
        key: "monitoring",
        permission: "monitoring.view_alert",
      },
      { label: "全局审计", key: "audit" },
    ],
  },
  { label: "系统设置", key: "settings", items: [] },
];
export function AppLayout({
  user,
  admin,
  path,
  onLogout,
  children,
}: {
  user: CurrentUser;
  admin: boolean;
  path: string;
  onLogout: () => void;
  children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false),
    [query, setQuery] = useState(""),
    [help, setHelp] = useState(false);
  const prefix = admin ? "/admin" : "/app",
    current = path.split("/")[2],
    go = (key: string) => navigate(prefix + "/" + key);
  const userItems: Item[] = [
    { label: "工作台", key: "dashboard" },
    { label: "我的虚拟机", key: "vms" },
    {
      label: "创建虚拟机",
      key: "vms/create",
      permission: "instances.add_instance",
    },
    { label: "远程控制台", key: "vms?console=1" },
    { label: "快照与备份", key: "snapshots", disabled: true },
    { label: "操作记录", key: "tasks" },
    { label: "个人设置", key: "profile" },
  ];
  const allowed = (item: Item) =>
    !item.permission || user.permissions.includes(item.permission);
  return (
    <div className={`console-layout ${collapsed ? "is-collapsed" : ""}`}>
      <header className="app-header">
        <button
          className="header-toggle"
          aria-label={collapsed ? "展开导航" : "折叠导航"}
          onClick={() => setCollapsed(!collapsed)}
        >
          ☰
        </button>
        <strong>CloudVirt</strong>
        <span className="header-divider">/</span>
        <span>{admin ? "管理控制台" : "用户控制台"}</span>
        <span className="header-spacer" />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            navigate(prefix + "/vms?search=" + encodeURIComponent(query));
          }}
        >
          <input
            aria-label="搜索虚拟机"
            placeholder="搜索虚拟机…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </form>
        <button className="action" onClick={() => go("tasks")}>
          任务
        </button>
        {admin ? (
          <button className="action" onClick={() => go("monitoring")}>
            告警
          </button>
        ) : null}
        <button className="action" onClick={() => setHelp(!help)}>
          帮助
        </button>
        <details className="user-menu">
          <summary>{user.display_name || user.username} ▾</summary>
          <div>
            <button onClick={() => go("profile")}>个人设置</button>
            <button onClick={onLogout}>退出登录</button>
          </div>
        </details>
      </header>
      <aside className="app-sidebar">
        <div className="sidebar-caption">
          {collapsed ? "CV" : admin ? "基础设施管理" : "个人资源管理"}
        </div>
        <nav aria-label="主导航">
          {admin
            ? groups.map((group) => (
                <div className="sidebar-group" key={group.key}>
                  <button
                    title={group.label}
                    className={current === group.key ? "active" : ""}
                    disabled={
                      group.key === "settings" ||
                      (group.key === "users" &&
                        !user.permissions.includes("accounts.manage_user"))
                    }
                    onClick={() => go(group.key)}
                  >
                    <span className="nav-icon">
                      {
                        (
                          {
                            dashboard: "◈",
                            vms: "▣",
                            storage: "▤",
                            networks: "◇",
                            users: "♙",
                            tasks: "≡",
                            settings: "⚙",
                          } as Record<string, string>
                        )[group.key]
                      }
                    </span>
                    {!collapsed ? group.label : null}
                  </button>
                  {!collapsed && group.items.length ? (
                    <div className="sidebar-sub">
                      {group.items.filter(allowed).map((item) => (
                        <button
                          key={item.key}
                          disabled={item.disabled}
                          title={
                            item.disabled ? "后端尚未提供此能力" : item.label
                          }
                          className={current === item.key ? "active" : ""}
                          onClick={() => go(item.key)}
                        >
                          {item.label}
                          {item.disabled ? <small>未开放</small> : null}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))
            : userItems.filter(allowed).map((item) => (
                <button
                  key={item.key}
                  title={item.disabled ? "后端尚未提供此能力" : item.label}
                  disabled={item.disabled}
                  className={path === prefix + "/" + item.key ? "active" : ""}
                  onClick={() => go(item.key)}
                >
                  {collapsed ? item.label.slice(0, 1) : item.label}
                </button>
              ))}
        </nav>
        <div className="sidebar-footer">
          {collapsed ? "●" : "● CloudVirt · QEMU / KVM"}
        </div>
      </aside>
      <main className="console-main">
        {help ? (
          <div className="banner banner-info">
            从资源列表进入详情；危险操作需确认，执行结果可在任务中心查询。未采集的指标显示“暂无数据”。
            <button className="action" onClick={() => setHelp(false)}>
              关闭
            </button>
          </div>
        ) : null}
        {children}
      </main>
    </div>
  );
}
