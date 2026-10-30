import { useCallback, useEffect, useState } from "react";
import { Drawer } from "../../components/ConsoleUI";
import { allResources } from "../infrastructure/client";
import { selectPermissions, type RolePermission } from "./permissionSelection";
import "./roles.css";
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
    [catalog, setCatalog] = useState<RolePermission[]>([]),
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
        api.request<{ results: RolePermission[] }>("/console/permissions"),
        allResources<{ id: number; name: string }>("/nodes"),
      ]);
      setRoles(r.results);
      setCatalog(p.results);
      setNodes(n);
      setError(null);
    } catch (error) {
      setError(describeError(error));
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  function edit(role: ManagedRole) {
    setError(null);
    setFilter("");
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
  function copy(role: ManagedRole) {
    setError(null);
    setFilter("");
    setEditing(null);
    setForm({ ...blank, display_name: `${role.display_name}副本`.slice(0, 64),
      description: role.description, scope: role.scope === "nodes" ? "nodes" : "owned",
      node_ids: role.scope === "nodes" ? [...role.node_ids] : [],
      permissions: selectPermissions([], role.permissions, true, catalog),
    });
  }
  function toggle(codes: string[], enabled: boolean) {
    setForm(current => ({ ...current,
      permissions: selectPermissions(current.permissions, codes, enabled, catalog),
    }));
  }
  const modules: Record<string, string> = {
    instances: "虚拟机、数据卷与快照", nodes: "物理节点", images: "镜像",
    networks: "网络", templates: "模板", tasks: "任务", monitoring: "监控",
  };
  const visible = catalog.filter(p => p.assignable &&
    `${p.code} ${p.name} ${modules[p.module] || p.module}`.toLowerCase().includes(filter.toLowerCase()));
  const moduleNames = [...new Set(visible.map(p => p.module))];
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
            setError(null);
            setFilter("");
            setEditing(null);
            setForm({ ...blank, node_ids: [], permissions: [] });
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
                    <button className="action" disabled={busy || !catalog.length} onClick={() => copy(role)}>
                      复制为新角色
                    </button>
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
        <Drawer wide title={editing === null ? "创建自定义角色" : "编辑角色与权限"}
          onClose={() => { if (!busy) setEditing(undefined); }}
          footer={<><span className="muted">已选 {form.permissions.length} 项权限</span>
            <button className="action" disabled={busy} onClick={() => setEditing(undefined)}>取消</button>
            <button form="role-editor" className="action primary" disabled={busy} type="submit">{busy ? "保存中…" : "保存角色"}</button></>}>
          <ErrorBanner message={error} />
          <form id="role-editor" className="role-editor" onSubmit={save}>
            <p className="banner banner-info">角色决定可执行操作，节点范围决定操作位置。自定义角色始终只访问本人资源；为用户分配多个角色时权限合并，配额不叠加。</p>
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
            <div className="role-permission-head"><h3>权限分配</h3><span className="perm-tag">已选 {form.permissions.length} 项</span></div>
            <input aria-label="搜索权限" placeholder="搜索模块、权限名称或编码" value={filter}
              onChange={e => setFilter(e.target.value)} />
            <p className="muted">勾选操作自动补齐查看权限；取消查看权限会同步移除依赖操作。管理员专属能力不开放给自定义角色。</p>
            <div className="role-permission-tools">
              <button type="button" className="action sm" disabled={busy || !visible.length}
                onClick={() => toggle(visible.map(p => p.code), true)}>选择当前搜索结果</button>
              <button type="button" className="action sm" disabled={busy || !form.permissions.length}
                onClick={() => setForm({ ...form, permissions: [] })}>清空权限</button>
            </div>
            {!moduleNames.length && <p className="empty">没有匹配的可分配权限。</p>}
            {moduleNames.map(module => {
              const items = visible.filter(p => p.module === module);
              return <section className="role-permission-module" key={module}>
                <div className="role-permission-head"><strong>{modules[module] || module}</strong>
                  <label><input type="checkbox" disabled={busy}
                    checked={items.every(p => form.permissions.includes(p.code))}
                    onChange={e => toggle(items.map(p => p.code), e.target.checked)} />选择本组</label>
                </div>
                <div className="role-permission-grid">{items.map(permission =>
                  <label className={form.permissions.includes(permission.code) ? "selected" : ""} key={permission.code}>
                    <input type="checkbox" disabled={busy} checked={form.permissions.includes(permission.code)}
                      onChange={e => toggle([permission.code], e.target.checked)} />
                    <span>{permission.name}<small>{permission.code}</small></span>
                  </label>
                )}</div>
              </section>;
            })}
          </form>
        </Drawer>
      )}
    </>
  );
}
