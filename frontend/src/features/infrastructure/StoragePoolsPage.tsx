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
type StorageVolume = {
  path: string;
  format: string;
  size_bytes: number;
  modified_at: string;
};
type VolumeResponse = {
  pool: string;
  path: string;
  results: StorageVolume[];
  truncated: boolean;
  sampled_at: string;
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
  const [selectedPool, setSelectedPool] = useState<StoragePool | null>(null);
  const [volumePool, setVolumePool] = useState<StoragePool | null>(null);
  const [volumeData, setVolumeData] = useState<VolumeResponse | null>(null);
  const [volumeSearch, setVolumeSearch] = useState("");
  const [volumeLoading, setVolumeLoading] = useState(false);
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
  const browseVolumes = async (pool: StoragePool) => {
    setSelectedPool(pool);
    setVolumePool(pool);
    setVolumeSearch("");
    setVolumeData(null);
    setVolumeLoading(true);
    setError(null);
    try {
      const response = await api.request<VolumeResponse>(
        `/admin/nodes/${node}/storage-pools/${encodeURIComponent(pool.name)}/volumes/`,
      );
      setVolumeData(response);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setVolumeLoading(false);
    }
  };
  const changePoolState = async (pool: StoragePool, action: "start" | "stop" | "refresh") => {
    if (action === "stop" && !window.confirm(`停止存储池 ${pool.name}？正在运行的虚拟机仍可访问已打开的磁盘文件，但不能再依赖此池执行新建或浏览操作。`)) return;
    setBusy(true);
    setError(null);
    try {
      await api.request(`/admin/nodes/${node}/storage-pools/${encodeURIComponent(pool.name)}/state/`, {
        method: "POST",
        body: JSON.stringify({ action }),
      });
      setSelectedPool(null);
      setRefresh((value) => value + 1);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <PageHeader
        title="存储池"
        description="按 virt-manager 的池与卷模型管理节点目录存储；选择一个池可查看容量、卷和运行状态"
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
          新建目录存储池
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
                      <tr
                        key={p.uuid || p.name}
                        className={selectedPool?.name === p.name ? "storage-pool-selected" : "storage-pool-row"}
                        onClick={() => setSelectedPool(p)}
                      >
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
                            <button className="action" disabled={!p.active || busy} onClick={(event) => { event.stopPropagation(); void browseVolumes(p); }}>
                              浏览卷
                            </button>
                          )}
                          {p.managed && (
                            <button className="action" onClick={(event) => {
                              event.stopPropagation();
                              setEditing(p);
                              setAssignedUsers(p.assigned_user_ids);
                              setDefaultUsers(p.default_user_ids);
                              setDefaultPool(p.is_default);
                              setError(null);
                            }}>分配使用权限</button>
                          )}
                          {p.managed && <button className="action danger" disabled={busy} onClick={async (event) => {
                            event.stopPropagation();
                            if (!window.confirm(`删除存储池 ${p.name}？仅移除空池定义与授权，保留目录；有关联资源或目录非空时将拒绝删除。`)) return;
                            setBusy(true); setError(null);
                            try {
                              await api.request(`/admin/nodes/${node}/storage-pools/${encodeURIComponent(p.name)}/access/`, { method: "DELETE" });
                              setRefresh((value) => value + 1);
                            } catch (err) { setError(describeError(err)); }
                            finally { setBusy(false); }
                          }}>删除</button>}
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
      {selectedPool && (
        <section className="card storage-pool-workbench" aria-label={`${selectedPool.name} 存储池详情`}>
          <header className="storage-pool-workbench-head">
            <div>
              <p className="eyebrow">已选择存储池</p>
              <h2>{selectedPool.name}</h2>
              <p className="muted">{selectedPool.type === "dir" ? "目录池" : selectedPool.type} · {selectedPool.target.path || "未提供目标路径"}</p>
            </div>
            <span className={`storage-pool-state ${selectedPool.active ? "active" : "inactive"}`}>{selectedPool.active ? "已激活" : "未激活"}</span>
          </header>
          <div className="storage-pool-detail-grid">
            <div className="storage-pool-capacity">
              <span>容量使用</span>
              <strong>{selectedPool.active ? `${formatBytes(selectedPool.allocation_bytes)} / ${formatBytes(selectedPool.capacity_bytes)}` : "池未激活"}</strong>
              <div className="storage-pool-meter" aria-label="存储池容量使用率"><i style={{ width: `${selectedPool.active && selectedPool.capacity_bytes ? Math.min(100, (selectedPool.allocation_bytes * 100) / selectedPool.capacity_bytes) : 0}%` }} /></div>
              <small>可用 {selectedPool.active ? formatBytes(selectedPool.available_bytes) : "—"}</small>
            </div>
            <dl className="storage-pool-facts">
              <div><dt>UUID</dt><dd>{selectedPool.uuid || "—"}</dd></div>
              <div><dt>平台管理</dt><dd>{selectedPool.managed ? "已纳管" : "只读发现"}</dd></div>
              <div><dt>使用授权</dt><dd>{selectedPool.managed ? `${selectedPool.assigned_user_ids.length} 位用户` : "—"}</dd></div>
              <div><dt>默认分配</dt><dd>{selectedPool.is_default ? "节点默认池" : selectedPool.default_user_ids.length ? `${selectedPool.default_user_ids.length} 位用户默认` : "未设置"}</dd></div>
            </dl>
          </div>
          <footer className="storage-pool-workbench-actions">
            {selectedPool.managed ? <>
              {selectedPool.active ? <button className="action" disabled={busy} onClick={() => void changePoolState(selectedPool, "refresh")}>刷新池</button> : <button className="action primary" disabled={busy} onClick={() => void changePoolState(selectedPool, "start")}>启动存储池</button>}
              {selectedPool.active && <button className="action danger" disabled={busy} onClick={() => void changePoolState(selectedPool, "stop")}>停止存储池</button>}
              <button className="action" disabled={!selectedPool.active || busy} onClick={() => void browseVolumes(selectedPool)}>浏览存储卷</button>
              <button className="action" disabled={busy} onClick={() => { setEditing(selectedPool); setAssignedUsers(selectedPool.assigned_user_ids); setDefaultUsers(selectedPool.default_user_ids); setDefaultPool(selectedPool.is_default); }}>配置授权</button>
            </> : <p className="muted">发现到的非托管池仅供查看；为避免绕过平台权限和目录校验，不能在此修改。</p>}
          </footer>
        </section>
      )}
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
      {volumePool && (
        <Drawer title={`存储卷 · ${volumePool.name}`} onClose={() => !volumeLoading && setVolumePool(null)}
          footer={<><span className="muted">卷操作请在镜像、数据卷或虚拟机页执行，避免绕过资源记录。</span><button className="action" disabled={volumeLoading} onClick={() => void browseVolumes(volumePool)}>刷新</button><button className="action" disabled={volumeLoading} onClick={() => setVolumePool(null)}>关闭</button></>}>
          <p className="muted">目录：{volumeData?.path || volumePool.target.path}</p>
          {volumeLoading && <p role="status">正在读取存储卷…</p>}
          {volumeData && <>
            <div className="storage-volume-summary">
              <span><strong>{volumeData.results.length}</strong> 个文件</span>
              <span><strong>{formatBytes(volumeData.results.reduce((total, volume) => total + volume.size_bytes, 0))}</strong> 实际占用</span>
              <span>采集于 {formatTime(volumeData.sampled_at)}</span>
            </div>
            <label className="storage-volume-search">筛选路径或格式
              <input value={volumeSearch} placeholder="例如 isos/、qcow2" onChange={(event) => setVolumeSearch(event.target.value)} />
            </label>
            <div className="table-scroll storage-volume-table"><table><thead><tr><th>相对路径</th><th>格式</th><th>实际大小</th><th>最后修改</th></tr></thead><tbody>
              {volumeData.results.filter((volume) => `${volume.path} ${volume.format}`.toLowerCase().includes(volumeSearch.toLowerCase())).map((volume) => <tr key={volume.path}><td><code>{volume.path}</code></td><td><span className="hardware-tag">{volume.format}</span></td><td>{formatBytes(volume.size_bytes)}</td><td>{formatTime(volume.modified_at)}</td></tr>)}
              {!volumeData.results.some((volume) => `${volume.path} ${volume.format}`.toLowerCase().includes(volumeSearch.toLowerCase())) && <tr><td colSpan={4} className="empty">没有匹配的存储卷。</td></tr>}
            </tbody></table></div>
            {volumeData.truncated && <p className="banner banner-info">卷数量超过 2000，当前仅显示前 2000 个文件；请使用更具体的目录或归档策略。</p>}
          </>}
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
