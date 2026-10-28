import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import { navigate } from "../../app/router";
import { Drawer, PageHeader } from "../../components/ConsoleUI";
import { Icon } from "../../components/icons";
import {
  Avatar,
  Card,
  DescList,
  EmptyState,
  ErrorBanner,
  LoadingState,
  Pagination,
  SearchInput,
  Segmented,
  StatusBadge,
  Tag,
  Toolbar,
  describeError,
  formatRelative,
  formatTimeFixed,
} from "../../components/ui";
import type { Paginated } from "../../types";
type Event = {
  id: number;
  actor_username: string;
  action: string;
  target_type: string;
  target_id: string;
  result: string;
  request_id: string;
  task_id?: string | null;
  created_at: string;
};
const PAGE_SIZE = 20;

/** 与后端 AuditAction 字典一致的中文名。 */
const ACTION_LABELS: Record<string, string> = {
  LOGIN_SUCCESS: "登录成功",
  LOGIN_FAILURE: "登录失败",
  LOGOUT: "登出",
  PASSWORD_CHANGE: "修改密码",
  PERMISSION_DENIED: "权限被拒",
  USER_CREATE: "创建用户",
  USER_UPDATE: "更新用户",
  USER_DISABLE: "禁用用户",
  USER_ENABLE: "启用用户",
  USER_DELETE: "删除用户",
  USER_PASSWORD_RESET: "重置用户密码",
  ROLE_CHANGE: "变更角色",
  NODE_REGISTER: "注册节点",
  NODE_UPDATE: "更新节点",
  NODE_REFRESH: "刷新节点资源",
  NODE_OFFLINE: "节点离线",
  IMAGE_IMPORT: "导入镜像",
  IMAGE_UPDATE: "更新镜像",
  IMAGE_DELETE: "删除镜像",
  INSTANCE_CREATE: "创建实例",
  INSTANCE_START: "启动实例",
  INSTANCE_SHUTDOWN: "关闭实例",
  INSTANCE_FORCE_STOP: "强制停止实例",
  INSTANCE_REBOOT: "重启实例",
  INSTANCE_DELETE: "删除实例",
  NETWORK_CREATE: "登记网络",
  NETWORK_UPDATE: "更新网络",
  NETWORK_DELETE: "删除网络",
  RECONCILE_RUN: "执行对账",
  TEMPLATE_CREATE: "创建模板",
  TEMPLATE_UPDATE: "更新模板",
  TEMPLATE_DELETE: "删除模板",
};
/** 操作分类：值为后端 search（action 包含匹配）关键字。 */
const CATEGORIES = [
  { value: "", label: "全部操作" },
  { value: "LOGIN", label: "登录认证" },
  { value: "INSTANCE", label: "虚拟机" },
  { value: "NODE", label: "节点" },
  { value: "IMAGE", label: "镜像" },
  { value: "NETWORK", label: "网络" },
  { value: "USER", label: "用户" },
  { value: "TEMPLATE", label: "模板" },
  { value: "PERMISSION", label: "权限拒绝" },
];
const TARGET_LABELS: Record<string, string> = {
  instance: "虚拟机",
  node: "节点",
  user: "用户",
  image: "镜像",
  network: "网络",
  template: "模板",
  cluster: "集群",
};
const DESTRUCTIVE = /DELETE|FORCE_STOP|DISABLE|DENIED|FAILURE|OFFLINE/;

type ResultFilter = "" | "SUCCESS" | "FAILURE" | "DENIED";

function resourceLink(e: Event): string | null {
  if (!/^\d+$/.test(e.target_id)) return null;
  if (e.target_type === "instance") return "/admin/vms/" + e.target_id;
  if (e.target_type === "node") return "/admin/nodes/" + e.target_id;
  return null;
}

export function AuditPage() {
  const [items, setItems] = useState<Event[]>([]),
    [page, setPage] = useState(1),
    [count, setCount] = useState(0),
    [error, setError] = useState<string | null>(null),
    [loading, setLoading] = useState(true),
    [category, setCategory] = useState(""),
    [keyword, setKeyword] = useState(""),
    [result, setResult] = useState<ResultFilter>(""),
    [refresh, setRefresh] = useState(0),
    [selected, setSelected] = useState<Event | null>(null);
  const admin = location.pathname.startsWith("/admin");
  useEffect(() => {
    let alive = true;
    setLoading(true);
    const params = new URLSearchParams({ page: String(page) });
    if (category) params.set("search", category);
    api
      .request<Paginated<Event>>("/console/audit?" + params)
      .then((p) => {
        if (alive) {
          setItems(p.results);
          setCount(p.count);
          setError(null);
        }
      })
      .catch((e) => {
        if (alive) setError(describeError(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [page, category, refresh]);

  // 账号 / 资源 / Request ID 关键字与结果筛选在当前页内进行（后端仅支持按操作检索）。
  const visible = useMemo(() => {
    const k = keyword.trim().toLowerCase();
    return items.filter(
      (e) =>
        (!result || e.result === result) &&
        (!k ||
          [
            e.actor_username,
            e.target_type + ":" + e.target_id,
            e.request_id,
            e.action,
            ACTION_LABELS[e.action] || "",
          ]
            .join(" ")
            .toLowerCase()
            .includes(k)),
    );
  }, [items, keyword, result]);
  const counts = useMemo(() => {
    const c: Record<string, number> = { SUCCESS: 0, FAILURE: 0, DENIED: 0 };
    for (const e of items) c[e.result] = (c[e.result] || 0) + 1;
    return c;
  }, [items]);
  const filtered = !!keyword.trim() || !!result;

  return (
    <>
      <PageHeader
        title="操作与审计日志"
        description="服务端记录的资源操作、认证与权限事件，只追加不可修改"
      >
        <button
          className="action"
          onClick={() => setRefresh((v) => v + 1)}
          disabled={loading}
        >
          <Icon name="refresh" size={15} />
          刷新
        </button>
      </PageHeader>
      <ErrorBanner message={error} />
      <Toolbar
        extra={
          filtered ? (
            <button
              className="action ghost"
              onClick={() => {
                setKeyword("");
                setResult("");
              }}
            >
              清除筛选
            </button>
          ) : null
        }
      >
        <SearchInput
          value={keyword}
          onChange={setKeyword}
          placeholder="账号、资源或 Request ID"
          width={260}
        />
        <select
          aria-label="操作类型"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setPage(1);
          }}
        >
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
        <Segmented<ResultFilter>
          label="结果"
          value={result}
          onChange={setResult}
          options={[
            { value: "", label: "全部" },
            { value: "SUCCESS", label: "成功", count: counts.SUCCESS },
            { value: "FAILURE", label: "失败", count: counts.FAILURE },
            { value: "DENIED", label: "拒绝", count: counts.DENIED },
          ]}
        />
      </Toolbar>
      <Card
        flush
        title="审计事件"
        description={
          filtered
            ? `当前页筛选出 ${visible.length} / ${items.length} 条 · 账号、资源与结果筛选仅作用于当前页`
            : `共 ${count} 条记录，按发生时间倒序`
        }
        footer={
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={count}
            onChange={setPage}
          />
        }
      >
        <div className="table-scroll">
          <table className="data-table audit-table">
            <thead>
              <tr>
                <th style={{ width: 176 }}>时间</th>
                <th style={{ width: 156 }}>操作者</th>
                <th>操作</th>
                <th style={{ width: 168 }}>资源</th>
                <th style={{ width: 96 }}>结果</th>
                <th className="col-reqid" style={{ width: 196 }}>
                  Request ID
                </th>
                <th className="col-actions" style={{ width: 72 }}>
                  详情
                </th>
              </tr>
            </thead>
            <tbody>
              {!loading &&
                visible.map((e) => {
                  const link = resourceLink(e);
                  return (
                    <tr key={e.id}>
                      <td>
                        <div className="cell-stack">
                          <span className="mono time-text">
                            {formatTimeFixed(e.created_at)}
                          </span>
                          <small className="muted">
                            {formatRelative(e.created_at)}
                          </small>
                        </div>
                      </td>
                      <td>
                        <span className="actor">
                          <Avatar name={e.actor_username || "系统"} />
                          <span className="truncate">
                            {e.actor_username || "系统"}
                          </span>
                        </span>
                      </td>
                      <td>
                        <div className="cell-inline">
                          <Tag
                            tone={DESTRUCTIVE.test(e.action) ? "warn" : "neutral"}
                            title={e.action}
                          >
                            {ACTION_LABELS[e.action] || e.action}
                          </Tag>
                          <span className="mono muted action-code">
                            {e.action}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div className="cell-inline">
                          <span className="muted">
                            {TARGET_LABELS[e.target_type] || e.target_type || "—"}
                          </span>
                          {link && admin ? (
                            <button
                              className="text-link mono"
                              onClick={() => navigate(link)}
                            >
                              #{e.target_id}
                            </button>
                          ) : (
                            <span className="mono truncate">
                              {e.target_id ? "#" + e.target_id : ""}
                            </span>
                          )}
                        </div>
                      </td>
                      <td>
                        <StatusBadge status={e.result} />
                      </td>
                      <td className="col-reqid">
                        <span
                          className="mono muted truncate"
                          title={e.request_id}
                        >
                          {e.request_id || "—"}
                        </span>
                      </td>
                      <td className="col-actions">
                        <button
                          className="icon-btn sm"
                          title="查看详情"
                          aria-label={`查看审计事件 ${e.id} 详情`}
                          onClick={() => setSelected(e)}
                        >
                          <Icon name="chevronRight" size={15} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
        {loading ? <LoadingState text="正在读取审计日志…" /> : null}
        {!loading && !visible.length ? (
          <EmptyState
            title={filtered || category ? "没有符合条件的记录" : "暂无操作记录"}
            description={
              filtered || category
                ? "调整筛选条件或切换页码后重试"
                : "资源操作和认证事件发生后会出现在这里"
            }
          />
        ) : null}
      </Card>
      {selected ? (
        <Drawer title="审计事件详情" onClose={() => setSelected(null)}>
          <div className="drawer-hero">
            <Tag tone={DESTRUCTIVE.test(selected.action) ? "warn" : "neutral"}>
              {ACTION_LABELS[selected.action] || selected.action}
            </Tag>
            <StatusBadge status={selected.result} />
          </div>
          <DescList
            columns={1}
            items={[
              ["事件 ID", <span className="mono">{selected.id}</span>],
              ["发生时间", <span className="mono">{formatTimeFixed(selected.created_at)}</span>],
              ["操作者", selected.actor_username || "系统"],
              ["操作代码", <span className="mono">{selected.action}</span>],
              [
                "资源",
                `${TARGET_LABELS[selected.target_type] || selected.target_type || "—"} ${selected.target_id ? "#" + selected.target_id : ""}`,
              ],
              ["Request ID", <span className="mono">{selected.request_id || "—"}</span>],
              ["关联任务", <span className="mono">{selected.task_id || "—"}</span>],
            ]}
          />
          <div className="drawer-actions">
            {resourceLink(selected) && admin ? (
              <button
                className="action"
                onClick={() => navigate(resourceLink(selected)!)}
              >
                查看资源
              </button>
            ) : null}
            {selected.task_id ? (
              <button
                className="action"
                onClick={() => navigate((admin ? "/admin" : "/app") + "/tasks")}
              >
                任务中心
              </button>
            ) : null}
          </div>
        </Drawer>
      ) : null}
    </>
  );
}
