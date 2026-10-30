import { useEffect, useRef, useState, type ReactNode } from "react";
import { navigate } from "../app/router";
import { Icon } from "../components/icons";
import { Avatar } from "../components/ui";
import type { CurrentUser } from "../types";

type Item = {
  label: string;
  key: string;
  icon: string;
  permission?: string;
  disabled?: boolean;
};
type Section = { label: string | null; key: string; items: Item[] };

/** 管理端导航：分组标题 + 图标菜单项。key 与路由第二段一致。 */
const adminSections: Section[] = [
  {
    label: null,
    key: "home",
    items: [{ label: "总览", key: "dashboard", icon: "dashboard" }],
  },
  {
    label: "计算资源",
    key: "compute",
    items: [
      { label: "集群", key: "clusters", icon: "cluster" },
      {
        label: "物理节点",
        key: "nodes",
        icon: "server",
        permission: "nodes.view_node",
      },
      {
        label: "虚拟机",
        key: "vms",
        icon: "vm",
        permission: "instances.view_instance",
      },
      { label: "资源池", key: "pools", icon: "pool" },
      {
        label: "部署模板",
        key: "templates",
        icon: "template",
        permission: "templates.view_template",
      },
    ],
  },
  {
    label: "存储管理",
    key: "storage-group",
    items: [
      { label: "数据卷", key: "storage", icon: "volume" },
      {
        label: "镜像",
        key: "images",
        icon: "image",
        permission: "images.view_image",
      },
      { label: "存储池", key: "storage-pools", icon: "storage" },
      { label: "快照", key: "snapshots", icon: "snapshot" },
    ],
  },
  {
    label: "网络与权限",
    key: "net",
    items: [
      { label: "网络管理", key: "networks", icon: "network" },
      { label: "用户与权限", key: "users", icon: "users" },
    ],
  },
  {
    label: "运维中心",
    key: "ops",
    items: [
      { label: "异步任务", key: "tasks", icon: "task" },
      {
        label: "监控与对账",
        key: "monitoring",
        icon: "monitor",
        permission: "monitoring.view_alert",
      },
      { label: "全局审计", key: "audit", icon: "audit" },
      { label: "系统设置", key: "settings", icon: "settings" },
    ],
  },
];

const userSections: Section[] = [
  {
    label: null,
    key: "home",
    items: [{ label: "工作台", key: "dashboard", icon: "dashboard" }],
  },
  {
    label: "我的资源",
    key: "res",
    items: [
      { label: "我的虚拟机", key: "vms", icon: "vm" },
      {
        label: "创建虚拟机",
        key: "vms/create",
        icon: "plus",
        permission: "instances.add_instance",
      },
      { label: "我的数据卷", key: "storage", icon: "storage", permission: "instances.view_instance" },
      { label: "远程控制台", key: "vms?console=1", icon: "console" },
      {
        label: "快照",
        key: "snapshots",
        icon: "snapshot",
        permission: "instances.view_instance",
      },
    ],
  },
  {
    label: "账号",
    key: "account",
    items: [
      { label: "操作记录", key: "tasks", icon: "task" },
      { label: "个人设置", key: "profile", icon: "user" },
    ],
  },
];

const EXTRA_LABELS: Record<string, string> = {
  roles: "用户与权限",
  profile: "个人设置",
  create: "创建",
};

/** 根据路由生成面包屑：控制台 / 分组 / 页面 / 详情。 */
function breadcrumb(path: string, admin: boolean, sections: Section[]) {
  const parts = path.split("/").filter(Boolean);
  const key = parts[1] || "dashboard";
  const crumbs: { label: string; to?: string }[] = [
    { label: admin ? "管理控制台" : "用户控制台", to: `/${parts[0]}/dashboard` },
  ];
  for (const section of sections) {
    const item = section.items.find((i) => i.key.split(/[/?]/)[0] === key);
    if (item) {
      if (section.label) crumbs.push({ label: section.label });
      crumbs.push({
        label: item.label,
        to: parts[2] ? `/${parts[0]}/${key}` : undefined,
      });
      break;
    }
  }
  if (crumbs.length === 1 && EXTRA_LABELS[key])
    crumbs.push({ label: EXTRA_LABELS[key] });
  if (parts[2])
    crumbs.push({
      label: parts[2] === "create" ? "创建" : /^\d+$/.test(parts[2]) ? `详情 #${parts[2]}` : parts[2],
    });
  if (parts[3] === "ssh" && /^\d+$/.test(parts[2] || "")) {
    crumbs[crumbs.length - 1].to = `/${parts[0]}/vms/${parts[2]}`;
    crumbs.push({ label: "Web SSH" });
  }
  return crumbs;
}

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
  const [collapsed, setCollapsed] = useState(
      () =>
        typeof window !== "undefined" &&
        !!window.matchMedia?.("(max-width: 900px)").matches,
    ),
    [query, setQuery] = useState(""),
    [help, setHelp] = useState(false),
    [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const prefix = admin ? "/admin" : "/app",
    current = path.split("/")[2] || "dashboard",
    go = (key: string) => navigate(prefix + "/" + key);
  const sections = admin ? adminSections : userSections;
  const allowed = (item: Item) =>
    !item.permission || user.permissions.includes(item.permission);
  const isDisabled = (item: Item) =>
    item.disabled ||
    (admin &&
      item.key === "users" &&
      !user.permissions.includes("accounts.manage_user"));
  const isActive = (item: Item) =>
    admin
      ? current === item.key || (item.key === "users" && current === "roles")
      : path === prefix + "/" + item.key ||
        (item.key === "vms" &&
          current === "vms" &&
          path.split("/")[3] !== "create");
  const crumbs = breadcrumb(path, admin, sections);
  const name = user.display_name || user.username;

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  return (
    <div className={`shell ${collapsed ? "is-collapsed" : ""}`}>
      <aside className="shell-side" aria-label="侧边导航">
        <div className="shell-side-inner">
        <div className="side-brand">
          <span className="side-logo" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
              <path
                d="M12 2.5 3.5 7.2v9.6L12 21.5l8.5-4.7V7.2z"
                fill="currentColor"
                opacity=".35"
              />
              <path d="M12 7.5 7.5 10v5L12 17.5l4.5-2.5v-5z" fill="currentColor" />
            </svg>
          </span>
          {!collapsed ? (
            <span className="side-brand-text">
              <strong>CloudVirt</strong>
              <small>{admin ? "基础设施管理" : "个人资源管理"}</small>
            </span>
          ) : null}
        </div>
        <nav aria-label="主导航" className="side-nav">
          {sections.map((section) => {
            const items = section.items.filter(allowed);
            if (!items.length) return null;
            return (
              <div className="side-section" key={section.key}>
                {section.label ? (
                  collapsed ? (
                    <hr className="side-divider" />
                  ) : (
                    <div className="side-section-label">{section.label}</div>
                  )
                ) : null}
                {items.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    title={
                      isDisabled(item)
                        ? item.disabled
                          ? "后端尚未提供此能力"
                          : "无用户管理权限"
                        : item.label
                    }
                    disabled={isDisabled(item)}
                    className={"side-item" + (isActive(item) ? " active" : "")}
                    aria-current={isActive(item) ? "page" : undefined}
                    onClick={() => go(item.key)}
                  >
                    <Icon name={item.icon} size={17} />
                    {!collapsed ? (
                      <span className="side-item-label">{item.label}</span>
                    ) : null}
                    {!collapsed && item.disabled ? <small>未开放</small> : null}
                  </button>
                ))}
              </div>
            );
          })}
        </nav>
        <div className="side-footer">
          <span className="side-status-dot" aria-hidden="true" />
          {!collapsed ? <span>QEMU / KVM · 服务正常</span> : null}
        </div>
        </div>
      </aside>
      <div className="shell-body">
        <header className="topbar">
          <button
            type="button"
            className="icon-btn"
            aria-label={collapsed ? "展开导航" : "折叠导航"}
            title={collapsed ? "展开导航" : "折叠导航"}
            onClick={() => setCollapsed(!collapsed)}
          >
            <Icon name={collapsed ? "expand" : "collapse"} size={17} />
          </button>
          <nav className="breadcrumb" aria-label="面包屑">
            {crumbs.map((c, i) => (
              <span className="crumb" key={i}>
                {i > 0 ? (
                  <Icon name="chevronRight" size={12} className="crumb-sep" />
                ) : null}
                {c.to && i < crumbs.length - 1 ? (
                  <button type="button" onClick={() => navigate(c.to!)}>
                    {c.label}
                  </button>
                ) : (
                  <span
                    className={i === crumbs.length - 1 ? "crumb-current" : ""}
                  >
                    {c.label}
                  </span>
                )}
              </span>
            ))}
          </nav>
          <span className="topbar-spacer" />
          <form
            className="topbar-search"
            role="search"
            onSubmit={(e) => {
              e.preventDefault();
              navigate(prefix + "/vms?search=" + encodeURIComponent(query));
            }}
          >
            <Icon name="search" size={15} />
            <input
              aria-label="搜索虚拟机"
              placeholder="搜索虚拟机名称或 UUID…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <kbd>↵</kbd>
          </form>
          <div className="topbar-actions">
            <button
              type="button"
              className="icon-btn"
              title="任务中心"
              aria-label="任务"
              onClick={() => go("tasks")}
            >
              <Icon name="task" size={17} />
            </button>
            {admin ? (
              <button
                type="button"
                className="icon-btn"
                title="告警"
                aria-label="告警"
                onClick={() => go("monitoring")}
              >
                <Icon name="bell" size={17} />
              </button>
            ) : null}
            <button
              type="button"
              className={"icon-btn" + (help ? " active" : "")}
              title="帮助"
              aria-label="帮助"
              aria-pressed={help}
              onClick={() => setHelp(!help)}
            >
              <Icon name="help" size={17} />
            </button>
          </div>
          <div className="user-menu" ref={menuRef}>
            <button
              type="button"
              className="user-menu-trigger"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen(!menuOpen)}
            >
              <Avatar name={name} size={28} />
              <span className="user-menu-name">
                <strong>{name}</strong>
                <small>{admin ? "管理员" : "用户"}</small>
              </span>
              <Icon name="chevronDown" size={14} />
            </button>
            {menuOpen ? (
              <div className="user-menu-pop" role="menu">
                <div className="user-menu-head">
                  <Avatar name={name} size={32} />
                  <div>
                    <strong>{name}</strong>
                    <small>@{user.username}</small>
                  </div>
                </div>
                <button
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false);
                    go("profile");
                  }}
                >
                  <Icon name="key" size={15} />
                  个人设置
                </button>
                <button
                  role="menuitem"
                  className="danger-text"
                  onClick={() => {
                    setMenuOpen(false);
                    onLogout();
                  }}
                >
                  <Icon name="logout" size={15} />
                  退出登录
                </button>
              </div>
            ) : null}
          </div>
        </header>
        <main className="console-main">
          <div className="console-content">
            {help ? (
              <div className="banner banner-info">
                从资源列表进入详情；危险操作需确认，执行结果可在任务中心查询。未采集的指标显示“暂无数据”。
                <button className="action sm" onClick={() => setHelp(false)}>
                  关闭
                </button>
              </div>
            ) : null}
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
