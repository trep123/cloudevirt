import { useEffect, useState } from "react";
import {
  PageHeader,
  Drawer,
  TaskProgressDrawer,
} from "../../components/ConsoleUI";
import { api } from "../../api";
import { newRequestId } from "../../utils/requestId";
import {
  ErrorBanner,
  describeError,
  formatBytes,
  formatTime,
} from "../../components/ui";
import type { Node } from "../../types";
import { infra, allResources, type Configuration } from "./client";

type StoragePool = {
  name: string;
  uuid: string;
  type: string;
  capacity_bytes: number;
  allocation_bytes: number;
  available_bytes: number;
  target: { path: string };
  active: boolean;
  managed: boolean;
  assigned_user_ids: number[];
  default_user_ids: number[];
  is_default: boolean;
  revision: number | null;
};
type UserOption = { id: number; username: string; is_active: boolean };
type PoolResponse = {
  storage_roots?: string[];
  default_directory?: string;
  results: StoragePool[];
  sampled_at: string;
  creatable_types: string[];
};
export function StoragePoolsPage() {
  const [nodes, setNodes] = useState<Node[]>([]),
    [node, setNode] = useState(0);
  const [users, setUsers] = useState<UserOption[]>([]);
  const [data, setData] = useState<PoolResponse | null>(null),
    [config, setConfig] = useState<Configuration | null>(null);
  const [error, setError] = useState<string | null>(null),
    [loading, setLoading] = useState(true);
  const [create, setCreate] = useState(false),
    [name, setName] = useState("cv-"),
    [key, setKey] = useState("");
  const [busy, setBusy] = useState(false),
    [task, setTask] = useState<string | null>(null),
    [refresh, setRefresh] = useState(0);
  const [directory, setDirectory] = useState("");
  const [assignedUsers, setAssignedUsers] = useState<number[]>([]);
  const [defaultUsers, setDefaultUsers] = useState<number[]>([]);
  const [defaultPool, setDefaultPool] = useState(false);
  const [editing, setEditing] = useState<StoragePool | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all([allResources<Node>("/nodes"), infra.configuration(), allResources<UserOption>("/users")])
      .then(([n, c, u]) => {
        if (live) {
          setNodes(n);
          setNode(n[0]?.id || 0);
          setConfig(c);
          setUsers(u.filter((item) => item.is_active));
          if (!n.length) setLoading(false);
        }
      })
      .catch((e) => {
        if (live) {
          setError(describeError(e));
          setLoading(false);
        }
      });
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    if (!node) return;
    let live = true;
    setLoading(true);
    setData(null);
    setError(null);
    api
      .request<PoolResponse>(`/admin/nodes/${node}/storage-pools/`)
      .then((p) => {
        if (live) setData(p);
      })
      .catch((e) => {
        if (live) setError(describeError(e));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [node, refresh]);
  return (
    <>
      <PageHeader
        title="存储池"
        description="查询节点 libvirt 存储池，可在允许的存储范围内指定目录创建目录池"
      >
        <select
          aria-label="所属节点"
          value={node}
          disabled={busy}
          onChange={(e) => setNode(Number(e.target.value))}
        >
          {nodes.map((n) => (
            <option key={n.id} value={n.id}>
              {n.name}
            </option>
          ))}
        </select>
        <button
          className="action"
          disabled={!node || loading}
          onClick={() => setRefresh((x) => x + 1)}
        >
          刷新状态
        </button>
        <button
          className="action primary"
          disabled={!data?.creatable_types.includes("dir") || busy}
          onClick={() => {
            setName("cv-");
            setKey(newRequestId());
            setDirectory("");
            setAssignedUsers([]);
            setDefaultUsers([]);
            setDefaultPool(false);
            setError(null);
            setCreate(true);
          }}
        >
          创建目录存储池
        </button>
      </PageHeader>
      <ErrorBanner message={error} />
      <p className="banner banner-info">
        同一文件系统上的多个池共享容量，不能相加作为节点总容量。新建池用于登记目录，现有虚拟机磁盘不会自动迁移。
      </p>
      <section className="card table-wrap">
        {loading ? (
          <p role="status">正在查询节点存储池…</p>
        ) : !nodes.length ? (
          <p className="empty">请先添加物理节点。</p>
        ) : null}
        {data ? (
          <>
            <p className="muted">成功采集时间：{formatTime(data.sampled_at)}</p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>名称 / UUID</th>
                    <th>类型</th>
                    <th>目录</th>
                    <th>容量</th>
                    <th>使用率</th>
                    <th>状态</th>
                    <th>授权用户 / 默认</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((p) => {
                    const percent = p.capacity_bytes
                      ? (p.allocation_bytes * 100) / p.capacity_bytes
                      : null;
                    const level =
                      percent !== null && config
                        ? percent >= config.storage_critical_percent
                          ? "高风险"
                          : percent >= config.storage_warning_percent
                            ? "警告"
                            : "正常"
                        : "—";
                    return (
                      <tr key={p.uuid || p.name}>
                        <td>
                          <strong>{p.name}</strong>
                          <p className="muted">{p.uuid}</p>
                        </td>
                        <td>{p.type}</td>
                        <td>{p.target.path || "—"}</td>
                        <td>
                          {p.active ? (
                            <>
                              {formatBytes(p.allocation_bytes)} /{" "}
                              {formatBytes(p.capacity_bytes)}
                              <p className="muted">
                                剩余 {formatBytes(p.available_bytes)}
                              </p>
                            </>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className={level === "正常" ? "" : "danger-text"}>
                          {p.active && percent !== null
                            ? `${percent.toFixed(1)}% · ${level}`
                            : "—"}
                        </td>
                        <td>{p.active ? "运行中" : "未激活"}</td>
                        <td>
                          {p.managed ? `${p.assigned_user_ids.length} 人` : "未纳管"}
                          {p.is_default ? " · 默认池" : ""}
                          {p.default_user_ids.length ? ` · ${p.default_user_ids.length} 人默认` : ""}
                        </td>
                        <td>
                          {p.managed && (
                            <button className="action" onClick={() => {
                              setEditing(p);
                              setAssignedUsers(p.assigned_user_ids);
                              setDefaultUsers(p.default_user_ids);
                              setDefaultPool(p.is_default);
                              setError(null);
                            }}>分配使用权限</button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {!data.results.length ? (
              <p className="empty">此节点暂无 libvirt 存储池。</p>
            ) : null}
          </>
        ) : null}
      </section>
      {create ? (
        <Drawer
          title="创建目录存储池"
          onClose={() => {
            if (!busy) setCreate(false);
          }}
          footer={
            <>
              <button
                className="action"
                type="button"
                disabled={busy}
                onClick={() => setCreate(false)}
              >
                取消
              </button>
              <button
                className="action primary"
                type="submit"
                form="storage-pool-form"
                disabled={busy}
              >
                {busy ? "提交中…" : "提交创建任务"}
              </button>
            </>
          }
        >
          <form
            id="storage-pool-form"
            className="infra-form"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError(null);
              try {
                const result = await infra.save(
                  `/admin/nodes/${node}/storage-pools/`,
                  { name, path: directory, assigned_user_ids: assignedUsers, default_user_ids: defaultUsers, is_default: defaultPool },
                  key,
                );
                setCreate(false);
                setTask(result.task_id);
              } catch (e) {
                setError(describeError(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            <ErrorBanner message={error} />
            <label>
              存储池名称
              <input
                required
                pattern="cv-[A-Za-z0-9][A-Za-z0-9_\-]{0,55}"
                maxLength={59}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              存储目录（绝对路径）
              <input
                value={directory}
                onChange={(e) => setDirectory(e.target.value)}
                placeholder={`${data?.default_directory || "受管目录"}/${name}`}
              />
              <small className="muted">
                留空使用默认目录；填写后将按指定目录创建或登记，不迁移现有磁盘。
              </small>
            </label>
            <div className="callout callout-muted">
              允许的根目录：
              {data?.storage_roots?.join("、") ||
                data?.default_directory ||
                "节点默认受管磁盘目录"}
              。不存在的子目录会自动创建；现有目录须已授予 Agent 与 QEMU
              访问权限。名称必须以 cv- 开头。
            </div>
            <label>
              允许使用的用户
              <select multiple value={assignedUsers.map(String)} onChange={(e) =>
                { const selected = Array.from(e.target.selectedOptions, (option) => Number(option.value)); setAssignedUsers(selected); setDefaultUsers((old) => old.filter((id) => selected.includes(id))); }}>
                {users.map((user) => <option key={user.id} value={user.id}>{user.username}</option>)}
              </select>
              <small className="muted">按 Ctrl / Cmd 可多选；平台管理员始终可使用。未分配的普通用户继续使用节点原有默认目录。</small>
            </label>
            <label>
              以此池为默认的用户
              <select multiple value={defaultUsers.map(String)} onChange={(e) =>
                setDefaultUsers(Array.from(e.target.selectedOptions, (option) => Number(option.value)))}>
                {users.filter((user) => assignedUsers.includes(user.id)).map((user) =>
                  <option key={user.id} value={user.id}>{user.username}</option>)}
              </select>
              <small className="muted">仅可选择已授权用户；同一用户在每个节点只有一个个人默认池。</small>
            </label>
            <label className="check">
              <input type="checkbox" checked={defaultPool} onChange={(e) => setDefaultPool(e.target.checked)} />
              设为此节点的默认存储池
            </label>
          </form>
        </Drawer>
      ) : null}
      {editing && (
        <Drawer title={`分配存储池 · ${editing.name}`} onClose={() => !busy && setEditing(null)}
          footer={<>
            <button className="action" disabled={busy} onClick={() => setEditing(null)}>取消</button>
            <button className="action primary" disabled={busy} form="pool-access-form" type="submit">{busy ? "保存中…" : "保存分配"}</button>
          </>}>
          <form id="pool-access-form" className="infra-form" onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              await api.request(`/admin/nodes/${node}/storage-pools/${encodeURIComponent(editing.name)}/access/`, {
                method: "PUT",
                body: JSON.stringify({ revision: editing.revision, assigned_user_ids: assignedUsers, default_user_ids: defaultUsers, is_default: defaultPool }),
              });
              setEditing(null);
              setRefresh((value) => value + 1);
            } catch (err) {
              setError(describeError(err));
            } finally {
              setBusy(false);
            }
          }}>
            <ErrorBanner message={error} />
            <p className="muted">目录：{editing.target.path}</p>
            <label>允许使用的用户
              <select multiple value={assignedUsers.map(String)} onChange={(e) =>
                { const selected = Array.from(e.target.selectedOptions, (option) => Number(option.value)); setAssignedUsers(selected); setDefaultUsers((old) => old.filter((id) => selected.includes(id))); }}>
                {users.map((user) => <option key={user.id} value={user.id}>{user.username}</option>)}
              </select>
            </label>
            <label>以此池为默认的用户
              <select multiple value={defaultUsers.map(String)} onChange={(e) =>
                setDefaultUsers(Array.from(e.target.selectedOptions, (option) => Number(option.value)))}>
                {users.filter((user) => assignedUsers.includes(user.id)).map((user) =>
                  <option key={user.id} value={user.id}>{user.username}</option>)}
              </select>
            </label>
            <label className="check">
              <input type="checkbox" checked={defaultPool} onChange={(e) => setDefaultPool(e.target.checked)} />
              设为此节点的默认存储池
            </label>
          </form>
        </Drawer>
      )}
      {task ? (
        <TaskProgressDrawer
          id={task}
          onClose={() => {
            setTask(null);
            setRefresh((x) => x + 1);
          }}
        />
      ) : null}
    </>
  );
}
