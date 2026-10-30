import { useCallback, useEffect, useRef, useState } from "react";
import { Drawer } from "../components/ConsoleUI";
import { api } from "../api";
import {
  Card,
  Empty,
  ErrorBanner,
  describeError,
  formatTime,
} from "../components/ui";
import { AccountBatchPanel } from "../features/users/AccountBatchPanel";
import type { ManagedRole } from "../features/users/RolesPage";
import type { User, AuditEvent, CurrentUser } from "../types";
type ManagedUser = User & {
  remark: string;
  node_scope: number[] | null;
  quota_overrides: Record<string, number>;
  status: string;
};
const quotaFields = ["instances", "vcpu", "memory_mib", "disk_gib"];
const quotaLabels: Record<string, string> = {
  instances: "虚拟机数量",
  vcpu: "vCPU",
  memory_mib: "内存 MiB",
  disk_gib: "磁盘 GiB",
};
const blank = {
  username: "",
  display_name: "",
  email: "",
  remark: "",
  password: "",
  roles: ["Viewer"],
  active: true,
  nodes: "*",
  quota: {} as Record<string, string>,
};
export function UsersPage() {
  const [users, setUsers] = useState<ManagedUser[]>([]),
    [roles, setRoles] = useState<ManagedRole[]>([]),
    [permissions, setPermissions] = useState<string[]>([]),
    [error, setError] = useState<string | null>(null),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  const [search, setSearch] = useState(""),
    [role, setRole] = useState(""),
    [active, setActive] = useState(""),
    [page, setPage] = useState(1),
    [total, setTotal] = useState(0),
    [selection, setSelection] = useState<number[]>([]);
  const [editing, setEditing] = useState<number | null | undefined>(undefined),
    [form, setForm] = useState(blank),
    [detail, setDetail] = useState<ManagedUser | null>(null),
    [audit, setAudit] = useState<AuditEvent[]>([]),
    [credential, setCredential] = useState<{
      username: string;
      password: string;
    } | null>(null);
  const generation = useRef(0);
  const reload = useCallback(async () => {
    const current = ++generation.current;
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: "20",
        search,
        role,
        active,
      });
      const result = await api.request<{
        results: ManagedUser[];
        count: number;
      }>(`/users?${params}`);
      if (current !== generation.current) return;
      setUsers(result.results);
      setTotal(result.count);
      setError(null);
    } catch (error) {
      if (current === generation.current) setError(describeError(error));
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, [page, search, role, active]);
  useEffect(() => {
    void reload();
  }, [reload]);
  useEffect(() => {
    void Promise.all([
      api.request<{ results: ManagedRole[] }>("/console/roles"),
      api.me(),
    ])
      .then(([result, user]: [{ results: ManagedRole[] }, CurrentUser]) => {
        setRoles(result.results);
        setPermissions(user.permissions);
      })
      .catch((error) => setError(describeError(error)));
  }, []);
  function edit(user: ManagedUser) {
    setEditing(user.id);
    setForm({
      username: user.username,
      display_name: user.display_name || "",
      email: user.email || "",
      remark: user.remark || "",
      password: "",
      roles: user.roles,
      active: user.is_active,
      nodes:
        user.node_scope === null
          ? "*"
          : user.node_scope?.length
            ? user.node_scope.join(";")
            : "[]",
      quota: Object.fromEntries(
        Object.entries(user.quota_overrides || {}).map(([key, value]) => [
          key,
          String(value),
        ]),
      ),
    });
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (
      editing !== null &&
      !window.confirm(
        `确认修改 ${form.username} 的信息和授权？角色、节点范围或状态变更将撤销旧会话。`,
      )
    )
      return;
    setBusy(true);
    setError(null);
    setCredential(null);
    try {
      const nodes =
        form.nodes.trim() === "*"
          ? null
          : form.nodes.trim() === "[]"
            ? []
            : form.nodes.split(";").map((value) => Number(value.trim()));
      if (nodes?.some((value) => !Number.isInteger(value) || value < 1))
        throw Error("节点范围填写 *、[] 或分号分隔的节点 ID");
      const quota = Object.fromEntries(
        Object.entries(form.quota)
          .filter(([, value]) => value !== "")
          .map(([key, value]) => [key, Number(value)]),
      );
      const payload = {
        display_name: form.display_name,
        email: form.email,
        remark: form.remark,
        roles: form.roles,
        is_active: form.active,
        node_scope: nodes,
        quota_overrides: quota,
        ...(editing === null
          ? { username: form.username, password: form.password }
          : {}),
      };
      await api.request(editing === null ? "/users" : `/users/${editing}`, {
        method: editing === null ? "POST" : "PATCH",
        body: JSON.stringify(payload),
      });
      setNotice(
        editing === null
          ? "账号已创建；未设置密码的新账号需先重置密码再启用"
          : "用户已更新，变更的授权将在服务端生效",
      );
      setEditing(undefined);
      setDetail(null);
      await reload();
    } catch (error) {
      setError(describeError(error));
    } finally {
      setBusy(false);
    }
  }
  async function toggle(user: ManagedUser) {
    if (
      !window.confirm(
        `确认${user.is_active ? "停用" : "启用"} ${user.username}？${user.is_active ? "旧登录和控制台会话将撤销。" : ""}`,
      )
    )
      return;
    setBusy(true);
    try {
      await api.updateUser(user.id, { is_active: !user.is_active });
      await reload();
    } catch (error) {
      setError(describeError(error));
    } finally {
      setBusy(false);
    }
  }
  async function reset(user: ManagedUser) {
    if (!window.confirm(`确认重置 ${user.username} 的密码？旧密码立即失效。`))
      return;
    setBusy(true);
    try {
      setCredential(await api.resetUserPassword(user.id));
      setNotice("临时密码仅显示一次，请通过受控渠道交付；禁用账号仍需手动启用");
      await reload();
    } catch (error) {
      setError(describeError(error));
    } finally {
      setBusy(false);
    }
  }
  async function show(user: ManagedUser) {
    setDetail(user);
    setAudit([]);
    try {
      setAudit((await api.userAudit(user.id)).results);
    } catch (error) {
      setError(describeError(error));
    }
  }
  function filter(update: () => void) {
    setPage(1);
    setSelection([]);
    update();
  }
  return (
    <>
      <ErrorBanner message={error} />
      {notice && <div className="banner banner-info">{notice}</div>}
      {credential && (
        <div className="banner banner-info">
          临时密码（关闭后不可查看）：{credential.username} /{" "}
          <code>{credential.password}</code>
          <button className="action" onClick={() => setCredential(null)}>
            我已记录
          </button>
        </div>
      )}
      <AccountBatchPanel
        selected={selection}
        filters={{ search, role, active }}
        onImported={reload}
        permissions={permissions}
      />
      <Card title={`用户管理 · 共 ${total} 个账号`}>
        <div className="toolbar">
          <input
            aria-label="搜索用户"
            value={search}
            placeholder="用户名、显示名或邮箱"
            onChange={(event) => filter(() => setSearch(event.target.value))}
          />
          <select
            aria-label="筛选角色"
            value={role}
            onChange={(event) => filter(() => setRole(event.target.value))}
          >
            <option value="">全部角色</option>
            {roles.map((item) => (
              <option key={item.id} value={item.code}>
                {item.display_name}
              </option>
            ))}
          </select>
          <select
            aria-label="筛选账号状态"
            value={active}
            onChange={(event) => filter(() => setActive(event.target.value))}
          >
            <option value="">全部状态</option>
            <option value="true">已启用</option>
            <option value="false">未启用</option>
          </select>
          <button
            className="action"
            disabled={busy}
            onClick={() => void reload()}
          >
            刷新
          </button>
          <button
            className="action primary"
            disabled={busy}
            onClick={() => {
              setEditing(null);
              setForm(blank);
            }}
          >
            创建用户
          </button>
        </div>
        {loading ? (
          <p role="status">正在加载用户…</p>
        ) : !users.length ? (
          <Empty text="暂无匹配用户" />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>
                    <input
                      aria-label="选择本页用户"
                      type="checkbox"
                      checked={
                        users.length > 0 &&
                        users.every((user) => selection.includes(user.id))
                      }
                      onChange={(event) =>
                        setSelection(
                          event.target.checked
                            ? [
                                ...new Set([
                                  ...selection,
                                  ...users.map((user) => user.id),
                                ]),
                              ]
                            : selection.filter(
                                (id) => !users.some((user) => user.id === id),
                              ),
                        )
                      }
                    />
                  </th>
                  <th>用户名 / 邮箱</th>
                  <th>显示名</th>
                  <th>角色</th>
                  <th>状态</th>
                  <th>节点范围</th>
                  <th>最近登录</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td>
                      <input
                        aria-label={`选择 ${user.username}`}
                        type="checkbox"
                        checked={selection.includes(user.id)}
                        onChange={(event) =>
                          setSelection(
                            event.target.checked
                              ? [...selection, user.id]
                              : selection.filter((id) => id !== user.id),
                          )
                        }
                      />
                    </td>
                    <td>
                      <strong>{user.username}</strong>
                      <div className="muted">{user.email || "—"}</div>
                    </td>
                    <td>{user.display_name || "—"}</td>
                    <td>
                      {user.roles
                        .map(
                          (code) =>
                            roles.find((item) => item.code === code)
                              ?.display_name || code,
                        )
                        .join("、") || "未分配"}
                    </td>
                    <td>
                      {user.status === "pending"
                        ? "待激活"
                        : user.is_active
                          ? "正常"
                          : "禁用"}
                      {user.must_change_password ? " · 需改密" : ""}
                    </td>
                    <td>
                      {user.node_scope === null
                        ? "继承授权"
                        : user.node_scope?.join("、") || "无节点"}
                    </td>
                    <td>{formatTime(user.last_login)}</td>
                    <td className="actions">
                      <button
                        className="action"
                        disabled={busy}
                        onClick={() => edit(user)}
                      >
                        编辑
                      </button>
                      <button
                        className="action"
                        onClick={() => void show(user)}
                      >
                        详情
                      </button>
                      <button
                        className="action"
                        disabled={busy}
                        onClick={() => void reset(user)}
                      >
                        重置密码
                      </button>
                      <button
                        className="action"
                        disabled={busy}
                        onClick={() => void toggle(user)}
                      >
                        {user.is_active ? "停用" : "启用"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="toolbar">
          <button
            className="action"
            disabled={page <= 1 || loading}
            onClick={() => setPage(page - 1)}
          >
            上一页
          </button>
          <span>第 {page} 页 · 每页 20 条</span>
          <button
            className="action"
            disabled={page * 20 >= total || loading}
            onClick={() => setPage(page + 1)}
          >
            下一页
          </button>
          <span>已选 {selection.length} 个</span>
        </div>
      </Card>
      {editing !== undefined && (
        <Drawer wide title={editing === null ? "创建用户" : `编辑 ${form.username}`}
          onClose={() => { if (!busy) setEditing(undefined); }}>
          <ErrorBanner message={error} />
          <form className="account-editor" onSubmit={save}>
            <div className="inline">
              <label>
                用户名
                <input
                  required
                  minLength={3}
                  maxLength={150}
                  disabled={editing !== null || busy}
                  value={form.username}
                  onChange={(event) =>
                    setForm({ ...form, username: event.target.value })
                  }
                />
              </label>
              <label>
                显示名
                <input
                  required
                  maxLength={64}
                  value={form.display_name}
                  onChange={(event) =>
                    setForm({ ...form, display_name: event.target.value })
                  }
                />
              </label>
              <label>
                邮箱
                <input
                  type="email"
                  value={form.email}
                  onChange={(event) =>
                    setForm({ ...form, email: event.target.value })
                  }
                />
              </label>
              <label>
                备注
                <input
                  maxLength={500}
                  value={form.remark}
                  onChange={(event) =>
                    setForm({ ...form, remark: event.target.value })
                  }
                />
              </label>
              {editing === null && (
                <label>
                  初始密码
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={form.password}
                    placeholder="留空创建待激活账号"
                    onChange={(event) =>
                      setForm({ ...form, password: event.target.value })
                    }
                  />
                </label>
              )}
              <fieldset className="account-role-options"><legend>角色（至少选择一个）</legend>
                {roles.filter(item => item.enabled || form.roles.includes(item.code)).map(item => (
                  <label key={item.id}><input type="checkbox" disabled={busy || (!item.enabled && !form.roles.includes(item.code))}
                    checked={form.roles.includes(item.code)} onChange={event => setForm({ ...form,
                      roles: event.target.checked ? [...form.roles, item.code] : form.roles.filter(code => code !== item.code),
                    })} /><span>{item.display_name}<small className="muted">{item.code}</small></span></label>
                ))}
              </fieldset>
              <label>
                节点范围
                <input
                  value={form.nodes}
                  onChange={(event) =>
                    setForm({ ...form, nodes: event.target.value })
                  }
                  placeholder="* 继承、[] 无节点、1;2 指定节点"
                />
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={form.active}
                  onChange={(event) =>
                    setForm({ ...form, active: event.target.checked })
                  }
                />
                启用（未初始化账号需先重置密码）
              </label>
            </div>
            <h3>账号配额覆盖</h3>
            <p className="muted">
              留空继承系统配额，0 表示禁止新增；降低配额不会删除或关闭已有资源。
            </p>
            <div className="inline">
              {quotaFields.map((key) => (
                <label key={key}>
                  {quotaLabels[key]}
                  <input
                    type="number"
                    min={0}
                    max={
                      key === "instances" || key === "vcpu"
                        ? 1000000
                        : 2147483647
                    }
                    value={form.quota[key] ?? ""}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        quota: { ...form.quota, [key]: event.target.value },
                      })
                    }
                  />
                </label>
              ))}
            </div>
            <button className="action primary" disabled={busy || !form.roles.length} type="submit">
              {busy ? "保存中…" : "保存用户"}
            </button>
            <button
              className="action"
              disabled={busy}
              type="button"
              onClick={() => setEditing(undefined)}
            >
              取消
            </button>
          </form>
        </Drawer>
      )}
      {detail && (
        <Drawer wide title={`用户详情：${detail.username}`} onClose={() => setDetail(null)}>
          <button className="action" onClick={() => setDetail(null)}>
            关闭详情
          </button>
          <p>资源配额覆盖：{JSON.stringify(detail.quota_overrides || {})}</p>
          <p>备注：{detail.remark || "—"}</p>
          <h3>有效操作权限</h3>
          <div className="perm-grid">
            {detail.permissions.map((permission) => (
              <span className="perm-tag" key={permission}>
                {permission}
              </span>
            ))}
          </div>
          <p className="muted">
            上述是操作权限集合，实际资源访问还需满足本人归属、角色节点范围及节点
            ACL。
          </p>
          <h3>最近操作</h3>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>动作</th>
                  <th>对象</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((event) => (
                  <tr key={event.id}>
                    <td>{formatTime(event.created_at)}</td>
                    <td>{event.action}</td>
                    <td>
                      {event.target_type}:{event.target_id}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Drawer>
      )}
    </>
  );
}
