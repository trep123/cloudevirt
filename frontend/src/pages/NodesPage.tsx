import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { navigate } from "../app/router";
import {
  Avatar,
  Card,
  EmptyState,
  ErrorBanner,
  Field,
  LoadingState,
  Meter,
  StatusBadge,
  Tag,
  describeError,
  formatBytes,
  formatRelative,
  formatTimeFixed,
} from "../components/ui";
import { PageHeader, ResourceStatCard } from "../components/ConsoleUI";
import { Icon } from "../components/icons";
import { can } from "../permissions";
import type { CurrentUser, Node, NodeAccess, User } from "../types";

const NODE_STATUSES = [
  "UNKNOWN",
  "ONLINE",
  "DEGRADED",
  "OFFLINE",
  "MAINTENANCE",
];

type NodeEditForm = {
  name: string;
  endpoint: string;
  status: string;
  maintenance_note: string;
  heartbeat_interval_seconds: number;
  offline_after_seconds: number;
};

export function NodesPage({ user }: { user: CurrentUser }) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [createName, setCreateName] = useState("");
  const [createEndpoint, setCreateEndpoint] = useState("");
  const [editing, setEditing] = useState<Node | null>(null);
  const [editForm, setEditForm] = useState<NodeEditForm | null>(null);

  const [accessNode, setAccessNode] = useState<Node | null>(null);
  const [accessRules, setAccessRules] = useState<NodeAccess[]>([]);
  const [accessUser, setAccessUser] = useState("");
  const [accessPermission, setAccessPermission] = useState("OPERATE");

  const canRegister = can(user, "nodes.add_node");
  const canRefresh = can(user, "nodes.refresh_node");
  const canGrant = can(user, "nodes.add_node");

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const page = await api.nodes();
      setNodes(page.results);
      setError(null);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!canGrant) return;
    api
      .users()
      .then((page) => setUsers(page.results))
      .catch(() => setUsers([]));
  }, [canGrant]);

  async function createNode(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.createNode({ name: createName, endpoint: createEndpoint });
      setNotice(`节点 ${createName} 已注册`);
      setCreateName("");
      setCreateEndpoint("");
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  function startEdit(node: Node) {
    setEditing(node);
    setEditForm({
      name: node.name,
      endpoint: node.endpoint,
      status: node.status,
      maintenance_note: node.maintenance_note || "",
      heartbeat_interval_seconds: node.heartbeat_interval_seconds,
      offline_after_seconds: node.offline_after_seconds,
    });
  }

  async function saveEdit(event: React.FormEvent) {
    event.preventDefault();
    if (!editing || !editForm) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.updateNode(editing.id, editForm);
      setNotice(`节点 ${editForm.name} 已更新`);
      setEditing(null);
      setEditForm(null);
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function removeNode(node: Node) {
    if (!window.confirm(`确认注销节点 ${node.name}？存在实例的节点无法注销。`))
      return;
    setError(null);
    setNotice(null);
    try {
      await api.deleteNode(node.id);
      setNotice(`节点 ${node.name} 已注销`);
      await reload();
    } catch (err) {
      setError(describeError(err));
    }
  }

  async function refresh(node: Node) {
    setError(null);
    try {
      await api.refreshNode(node.id);
      setNotice(`节点 ${node.name} 资源已刷新`);
      await reload();
    } catch (err) {
      setError(describeError(err));
    }
  }

  async function loadAccess(node: Node) {
    setAccessNode(node);
    setAccessUser("");
    try {
      const page = await api.nodeAccess(node.id);
      setAccessRules(page.results);
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }

  async function grantAccess() {
    if (!accessNode || !accessUser) return;
    setError(null);
    try {
      await api.createNodeAccess({
        node: accessNode.id,
        user: Number(accessUser),
        permission: accessPermission,
      });
      setAccessUser("");
      const page = await api.nodeAccess(accessNode.id);
      setAccessRules(page.results);
      setNotice("节点授权已保存");
    } catch (err) {
      setError(describeError(err));
    }
  }

  async function revokeAccess(rule: NodeAccess) {
    setError(null);
    try {
      await api.deleteNodeAccess(rule.id);
      if (accessNode) {
        const page = await api.nodeAccess(accessNode.id);
        setAccessRules(page.results);
      }
      setNotice("节点授权已撤销");
    } catch (err) {
      setError(describeError(err));
    }
  }

  const [showRegister, setShowRegister] = useState(false);
  const counts = {
    online: nodes.filter((n) => n.status === "ONLINE").length,
    degraded: nodes.filter((n) => n.status === "DEGRADED").length,
    offline: nodes.filter((n) => n.status === "OFFLINE" || n.status === "UNKNOWN").length,
    maintenance: nodes.filter((n) => n.status === "MAINTENANCE").length,
  };
  const memPct = (n: Node) =>
    n.memory_total_mib && n.memory_available_mib != null
      ? Math.round(((n.memory_total_mib - n.memory_available_mib) / n.memory_total_mib) * 100)
      : null;
  const diskPct = (n: Node) =>
    n.storage_total_bytes && n.storage_free_bytes != null
      ? Math.round(((n.storage_total_bytes - n.storage_free_bytes) / n.storage_total_bytes) * 100)
      : null;
  const gb = (mib: number | null) => (mib == null ? "—" : `${Math.round(mib / 1024)} GB`);

  return (
    <>
      <PageHeader
        title="物理节点"
        description="登记 KVM 宿主机 Agent，查看资源采样、调度状态与访问授权"
      >
        <button className="action" onClick={() => void reload()}>
          <Icon name="refresh" size={15} />
          刷新列表
        </button>
        {canRegister ? (
          <button
            className="action primary"
            onClick={() => setShowRegister(!showRegister)}
            aria-expanded={showRegister}
          >
            <Icon name={showRegister ? "close" : "plus"} size={15} />
            {showRegister ? "收起" : "注册节点"}
          </button>
        ) : null}
      </PageHeader>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      <div className="resource-stats">
        <ResourceStatCard
          label="节点总数"
          icon="server"
          value={nodes.length}
          note={`${nodes.filter((n) => n.is_schedulable).length} 个可调度`}
        />
        <ResourceStatCard
          label="在线"
          icon="check"
          tone="ok"
          value={counts.online}
          note="心跳正常的节点"
        />
        <ResourceStatCard
          label="降级 / 维护"
          icon="alert"
          tone="warn"
          value={counts.degraded + counts.maintenance}
          note={`${counts.degraded} 降级 · ${counts.maintenance} 维护中`}
        />
        <ResourceStatCard
          label="离线 / 未知"
          icon="power"
          tone={counts.offline ? "bad" : "brand"}
          value={counts.offline}
          note="超过离线阈值未上报"
        />
      </div>
      {canRegister && showRegister ? (
        <Card
          title="注册节点"
          description="在宿主机部署 cv-agent 后，填写 Agent 访问地址完成登记"
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void createNode(e);
            }}
          >
            <div className="form-grid">
              <Field label="名称" hint="建议使用主机名，如 kvm-node-01">
                <input
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  placeholder="node-01"
                  required
                />
              </Field>
              <Field label="Agent 地址" hint="管理服务可访问的 HTTP 地址">
                <input
                  value={createEndpoint}
                  onChange={(e) => setCreateEndpoint(e.target.value)}
                  placeholder="http://10.0.0.11:9100"
                  required
                />
              </Field>
            </div>
            <div className="form-actions">
              <button
                className="action"
                type="button"
                onClick={() => setShowRegister(false)}
              >
                取消
              </button>
              <button className="action primary" type="submit" disabled={busy}>
                {busy ? "提交中…" : "注册"}
              </button>
            </div>
          </form>
        </Card>
      ) : null}
      {editing && editForm ? (
        <Card
          title={`编辑节点：${editing.name}`}
          description="修改连接信息、调度状态与采集参数"
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void saveEdit(e);
            }}
          >
            <div className="form-grid">
              <Field label="名称">
                <input
                  value={editForm.name}
                  onChange={(e) =>
                    setEditForm({ ...editForm, name: e.target.value })
                  }
                  required
                />
              </Field>
              <Field label="Agent 地址">
                <input
                  value={editForm.endpoint}
                  onChange={(e) =>
                    setEditForm({ ...editForm, endpoint: e.target.value })
                  }
                  required
                />
              </Field>
              <Field label="状态">
                <select
                  value={editForm.status}
                  onChange={(e) =>
                    setEditForm({ ...editForm, status: e.target.value })
                  }
                >
                  {NODE_STATUSES.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="采集周期(秒)" hint="5–3600">
                <input
                  type="number"
                  min={5}
                  max={3600}
                  value={editForm.heartbeat_interval_seconds}
                  onChange={(e) =>
                    setEditForm({
                      ...editForm,
                      heartbeat_interval_seconds: Number(e.target.value),
                    })
                  }
                />
              </Field>
              <Field label="离线阈值(秒)" hint="10–7200">
                <input
                  type="number"
                  min={10}
                  max={7200}
                  value={editForm.offline_after_seconds}
                  onChange={(e) =>
                    setEditForm({
                      ...editForm,
                      offline_after_seconds: Number(e.target.value),
                    })
                  }
                />
              </Field>
              <Field label="维护说明">
                <input
                  value={editForm.maintenance_note}
                  onChange={(e) =>
                    setEditForm({ ...editForm, maintenance_note: e.target.value })
                  }
                  placeholder="可选"
                />
              </Field>
            </div>
            <div className="form-actions">
              <button
                className="action"
                type="button"
                onClick={() => {
                  setEditing(null);
                  setEditForm(null);
                }}
              >
                取消
              </button>
              <button className="action primary" type="submit" disabled={busy}>
                {busy ? "保存中…" : "保存"}
              </button>
            </div>
          </form>
        </Card>
      ) : null}
      <Card flush title="节点列表" description={`共 ${nodes.length} 个节点`}>
        {loading && !nodes.length ? (
          <LoadingState text="加载中…" />
        ) : nodes.length === 0 ? (
          <EmptyState
            icon="server"
            title="尚未注册节点"
            description="请先在宿主机部署 Agent 并登记地址。"
          />
        ) : (
          <div className="table-scroll">
            <table className="data-table node-table">
              <thead>
                <tr>
                  <th>名称</th>
                  <th>状态</th>
                  <th className="num">CPU</th>
                  <th>内存使用</th>
                  <th>存储使用</th>
                  <th>采样时间</th>
                  <th>Agent</th>
                  <th className="col-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((node) => {
                  const mp = memPct(node),
                    dp = diskPct(node);
                  return (
                    <tr key={node.id}>
                      <td>
                        <div className="cell-stack">
                          <button
                            className="text-link"
                            onClick={() => navigate("/admin/nodes/" + node.id)}
                          >
                            {node.name}
                          </button>
                          <small className="mono muted">{node.endpoint}</small>
                        </div>
                      </td>
                      <td>
                        <div className="cell-stack">
                          <span>
                            <StatusBadge status={node.status} />
                          </span>
                          {node.resource_is_stale ? (
                            <small className="stale-label">数据已过期</small>
                          ) : node.maintenance_note ? (
                            <small className="muted truncate" title={node.maintenance_note}>
                              {node.maintenance_note}
                            </small>
                          ) : null}
                        </div>
                      </td>
                      <td className="num spec-text">
                        {node.cpu_total ?? "—"} 核
                      </td>
                      <td>
                        <div className="usage-cell">
                          <Meter value={mp} />
                          <small>
                            {mp == null ? "—" : `${mp}%`} ·{" "}
                            {gb(node.memory_available_mib)} 可用 / {gb(node.memory_total_mib)}
                          </small>
                        </div>
                      </td>
                      <td>
                        <div className="usage-cell">
                          <Meter value={dp} />
                          <small>
                            {dp == null ? "—" : `${dp}%`} ·{" "}
                            {formatBytes(node.storage_free_bytes)} 可用
                          </small>
                        </div>
                      </td>
                      <td>
                        <span
                          className="time-text"
                          title={formatTimeFixed(node.resource_sampled_at)}
                        >
                          {formatRelative(node.resource_sampled_at) || "—"}
                        </span>
                      </td>
                      <td>
                        <div className="cell-stack">
                          <span className="mono">{node.agent_version || "—"}</span>
                          {node.last_error_message ? (
                            <small className="danger-text" title={node.last_error_message}>
                              {node.last_error_code}
                            </small>
                          ) : null}
                        </div>
                      </td>
                      <td className="col-actions">
                        <div className="row-actions">
                          {canRefresh ? (
                            <button
                              className="action sm"
                              title="刷新资源"
                              onClick={() => void refresh(node)}
                            >
                              <Icon name="refresh" size={14} />
                              刷新
                            </button>
                          ) : null}
                          {canRegister ? (
                            <button
                              className="action sm"
                              onClick={() => startEdit(node)}
                            >
                              编辑
                            </button>
                          ) : null}
                          <details className="row-menu">
                            <summary>
                              更多 <Icon name="chevronDown" size={13} />
                            </summary>
                            <div>
                              <button onClick={() => navigate("/admin/nodes/" + node.id)}>
                                查看详情
                              </button>
                              <button onClick={() => void loadAccess(node)}>
                                访问授权
                              </button>
                              {canRegister ? (
                                <button
                                  className="danger-text"
                                  onClick={() => void removeNode(node)}
                                >
                                  注销节点
                                </button>
                              ) : null}
                            </div>
                          </details>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {accessNode ? (
        <Card
          title={`节点授权：${accessNode.name}`}
          description="无授权记录时全部放行；存在记录后非管理员只能访问被授权节点。"
          extra={
            <button className="action sm" onClick={() => setAccessNode(null)}>
              关闭
            </button>
          }
        >
          {canGrant ? (
            <form
              className="access-form"
              onSubmit={(e) => {
                e.preventDefault();
                void grantAccess();
              }}
            >
              <Field label="用户">
                <select
                  value={accessUser}
                  onChange={(e) => setAccessUser(e.target.value)}
                  required
                >
                  <option value="">选择用户</option>
                  {users.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.username}
                      {item.display_name ? `（${item.display_name}）` : ""}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="权限">
                <select
                  value={accessPermission}
                  onChange={(e) => setAccessPermission(e.target.value)}
                >
                  <option value="OPERATE">操作</option>
                  <option value="VIEW">查看</option>
                </select>
              </Field>
              <button className="action primary" type="submit">
                授权
              </button>
            </form>
          ) : null}
          {accessRules.length === 0 ? (
            <EmptyState
              icon="key"
              title="无授权记录"
              description="默认全部放行"
            />
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>用户/组</th>
                  <th>权限</th>
                  <th>创建时间</th>
                  <th className="col-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                {accessRules.map((rule) => (
                  <tr key={rule.id}>
                    <td>
                      <span className="actor">
                        <Avatar name={rule.username || rule.group_name || "-"} />
                        {rule.username || rule.group_name || "-"}
                      </span>
                    </td>
                    <td>
                      <Tag tone={rule.permission === "OPERATE" ? "brand" : "neutral"}>
                        {rule.permission === "OPERATE" ? "操作" : rule.permission === "VIEW" ? "查看" : rule.permission}
                      </Tag>
                    </td>
                    <td className="mono time-text">{formatTimeFixed(rule.created_at)}</td>
                    <td className="col-actions">
                      {canGrant ? (
                        <button
                          className="action sm danger"
                          onClick={() => void revokeAccess(rule)}
                        >
                          撤销
                        </button>
                      ) : (
                        "-"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      ) : null}
    </>
  );
}
