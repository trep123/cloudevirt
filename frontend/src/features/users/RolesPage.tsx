import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import { Card, ErrorBanner, describeError } from "../../components/ui";
export type ManagedRole = {
  id: number;
  code: string;
  name: string;
  display_name: string;
  description: string;
  enabled: boolean;
  builtin: boolean;
  scope: string;
  node_ids: number[];
  permissions: string[];
  user_count: number;
  revision: number;
};
type Permission = {
  code: string;
  name: string;
  module: string;
  assignable: boolean;
};
const blank = {
  code: "",
  display_name: "",
  description: "",
  enabled: true,
  scope: "owned",
  node_ids: [] as number[],
  permissions: [] as string[],
  revision: 0,
};
export function RolesPage() {
  const [roles, setRoles] = useState<ManagedRole[]>([]),
    [catalog, setCatalog] = useState<Permission[]>([]),
    [nodes, setNodes] = useState<{ id: number; name: string }[]>([]),
    [error, setError] = useState<string | null>(null),
    [editing, setEditing] = useState<number | null | undefined>(undefined),
    [form, setForm] = useState(blank),
    [busy, setBusy] = useState(false),
    [filter, setFilter] = useState("");
  const reload = useCallback(async () => {
    try {
      const [r, p, n] = await Promise.all([
        api.request<{ results: ManagedRole[] }>("/console/roles"),
        api.request<{ results: Permission[] }>("/console/permissions"),
        api.nodes(),
      ]);
      setRoles(r.results);
      setCatalog(p.results);
      setNodes(n.results);
      setError(null);
    } catch (error) {
      setError(describeError(error));
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  function edit(role: ManagedRole) {
    setEditing(role.id);
    setForm({
      code: role.code,
      display_name: role.display_name,
      description: role.description,
      enabled: role.enabled,
      scope: role.scope,
      node_ids: role.node_ids,
      permissions: role.permissions,
      revision: role.revision,
    });
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    const count = roles.find((role) => role.id === editing)?.user_count || 0;
    if (
      count &&
      !window.confirm(
        `此次变更影响 ${count} 个用户，并撤销其旧登录和控制台会话，是否继续？`,
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      await api.request(
        editing === null ? "/console/roles" : `/console/roles/${editing}`,
        {
          method: editing === null ? "POST" : "PATCH",
          body: JSON.stringify(form),
        },
      );
      setEditing(undefined);
      await reload();
    } catch (error) {
      setError(describeError(error));
    } finally {
      setBusy(false);
    }
  }
  async function remove(role: ManagedRole) {
    if (
      !window.confirm(
        `确认删除角色 ${role.display_name}（${role.code}）？不会删除用户和虚拟机。`,
      )
    )
      return;
    setBusy(true);
    try {
      await api.request(`/console/roles/${role.id}`, { method: "DELETE" });
      await reload();
    } catch (error) {
      setError(describeError(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <ErrorBanner message={error} />
      <Card title="角色管理">
        <button
          className="action primary"
          disabled={busy}
          onClick={() => {
            setEditing(null);
            setForm(blank);
          }}
        >
          创建自定义角色
        </button>
        <button className="action" onClick={() => void reload()}>
          刷新
        </button>
        <p className="muted">
          角色不隐式继承；操作权限与节点范围配套生效，普通账号仍只能访问本人资源。内置角色只读，多角色不叠加配额。
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>名称 / 编码</th>
                <th>范围</th>
                <th>状态</th>
                <th>权限</th>
                <th>用户数</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {roles.map((role) => (
                <tr key={role.id}>
                  <td>
                    <strong>{role.display_name}</strong>
                    <div className="muted">
                      {role.code} {role.builtin ? "· 内置" : ""}
                    </div>
                    <small>{role.description}</small>
                  </td>
                  <td>
                    {role.scope === "global"
                      ? "全平台"
                      : role.scope === "owned"
                        ? "本人资源"
                        : `节点：${role.node_ids.map((id) => nodes.find((node) => node.id === id)?.name || id).join("、")}`}
                  </td>
                  <td>{role.enabled ? "启用" : "禁用"}</td>
                  <td>
                    <details>
                      <summary>{role.permissions.length} 项</summary>
                      {role.permissions.map((permission) => (
                        <div key={permission} className="mono">
                          {permission}
                        </div>
                      ))}
                    </details>
                  </td>
                  <td>{role.user_count}</td>
                  <td>
                    <button
                      className="action"
                      disabled={busy || role.builtin}
                      onClick={() => edit(role)}
                    >
                      编辑
                    </button>
                    <button
                      className="action danger"
                      disabled={busy || role.builtin || role.user_count > 0}
                      title={role.user_count ? "请先迁移关联用户" : undefined}
                      onClick={() => void remove(role)}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {editing !== undefined && (
        <Card title={editing === null ? "创建角色" : "编辑角色"}>
          <form onSubmit={save}>
            <div className="inline">
              <label>
                角色编码
                <input
                  required
                  value={form.code}
                  disabled={editing !== null || busy}
                  pattern="[a-z][a-z0-9_]{2,47}"
                  onChange={(e) => setForm({ ...form, code: e.target.value })}
                />
              </label>
              <label>
                显示名称
                <input
                  required
                  maxLength={64}
                  value={form.display_name}
                  onChange={(e) =>
                    setForm({ ...form, display_name: e.target.value })
                  }
                />
              </label>
              <label>
                说明
                <input
                  maxLength={500}
                  value={form.description}
                  onChange={(e) =>
                    setForm({ ...form, description: e.target.value })
                  }
                />
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(e) =>
                    setForm({ ...form, enabled: e.target.checked })
                  }
                />
                启用
              </label>
              <label>
                范围
                <select
                  value={form.scope}
                  onChange={(e) =>
                    setForm({ ...form, scope: e.target.value, node_ids: [] })
                  }
                >
                  <option value="owned">授权节点上的本人资源</option>
                  <option value="nodes">指定节点上的本人资源</option>
                </select>
              </label>
            </div>
            {form.scope === "nodes" && (
              <div className="perm-grid">
                {nodes.map((node) => (
                  <label key={node.id}>
                    <input
                      type="checkbox"
                      checked={form.node_ids.includes(node.id)}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          node_ids: e.target.checked
                            ? [...form.node_ids, node.id]
                            : form.node_ids.filter((id) => id !== node.id),
                        })
                      }
                    />
                    {node.name}
                  </label>
                ))}
              </div>
            )}
            <h3>权限分配</h3>
            <input
              aria-label="搜索权限"
              placeholder="按权限名称、编码搜索"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <p className="muted">
              操作权限需要同时选择对应查看权限。灰色权限仅属于内置管理员或尚未开放独立授权。
            </p>
            <div
              className="perm-grid"
              style={{ maxHeight: 320, overflow: "auto" }}
            >
              {catalog
                .filter((permission) =>
                  (permission.code + " " + permission.name)
                    .toLowerCase()
                    .includes(filter.toLowerCase()),
                )
                .map((permission) => (
                  <label key={permission.code}>
                    <input
                      type="checkbox"
                      disabled={!permission.assignable || busy}
                      checked={form.permissions.includes(permission.code)}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          permissions: e.target.checked
                            ? [...form.permissions, permission.code]
                            : form.permissions.filter(
                                (code) => code !== permission.code,
                              ),
                        })
                      }
                    />
                    {permission.name}
                    <small className="muted"> {permission.code}</small>
                  </label>
                ))}
            </div>
            <button className="action primary" disabled={busy} type="submit">
              {busy ? "保存中…" : "保存角色"}
            </button>
            <button
              className="action"
              type="button"
              disabled={busy}
              onClick={() => setEditing(undefined)}
            >
              取消
            </button>
          </form>
        </Card>
      )}
    </>
  );
}
