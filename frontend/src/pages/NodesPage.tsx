import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { navigate } from "../app/router";
import {
  Card,
  Empty,
  ErrorBanner,
  StatusBadge,
  describeError,
  formatBytes,
  formatTime,
} from "../components/ui";
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

  return (
    <>
      <div className="page-head">
        <h2>节点</h2>
        <button className="action" onClick={() => void reload()}>
          刷新列表
        </button>
      </div>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      {canRegister ? (
        <Card title="注册节点">
          <form
            className="inline"
            onSubmit={(e) => {
              e.preventDefault();
              void createNode(e);
            }}
          >
            <label>
              名称
              <input
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder="node-01"
                required
              />
            </label>
            <label>
              Agent 地址
              <input
                value={createEndpoint}
                onChange={(e) => setCreateEndpoint(e.target.value)}
                placeholder="http://10.0.0.11:9100"
                required
              />
            </label>
            <button className="action primary" type="submit" disabled={busy}>
              {busy ? "提交中…" : "注册"}
            </button>
          </form>
        </Card>
      ) : null}
      {editing && editForm ? (
        <Card title={`编辑节点：${editing.name}`}>
          <form
            className="inline"
            onSubmit={(e) => {
              e.preventDefault();
              void saveEdit(e);
            }}
          >
            <label>
              名称
              <input
                value={editForm.name}
                onChange={(e) =>
                  setEditForm({ ...editForm, name: e.target.value })
                }
                required
              />
            </label>
            <label>
              Agent 地址
              <input
                value={editForm.endpoint}
                onChange={(e) =>
                  setEditForm({ ...editForm, endpoint: e.target.value })
                }
                required
              />
            </label>
            <label>
              状态
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
            </label>
            <label>
              采集周期(秒)
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
            </label>
            <label>
              离线阈值(秒)
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
            </label>
            <label>
              维护说明
              <input
                value={editForm.maintenance_note}
                onChange={(e) =>
                  setEditForm({ ...editForm, maintenance_note: e.target.value })
                }
                placeholder="可选"
              />
            </label>
            <button className="action primary" type="submit" disabled={busy}>
              {busy ? "保存中…" : "保存"}
            </button>
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
          </form>
        </Card>
      ) : null}
      <Card title={`共 ${nodes.length} 个节点`}>
        {loading ? (
          <Empty text="加载中…" />
        ) : nodes.length === 0 ? (
          <Empty text="尚未注册节点，请先部署 Agent 并登记地址。" />
        ) : (
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>状态</th>
                <th>CPU</th>
                <th>内存</th>
                <th>存储可用</th>
                <th>采样时间</th>
                <th>Agent</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {nodes.map((node) => (
                <tr key={node.id}>
                  <td>
                    <button
                      className="text-link"
                      onClick={() => navigate("/admin/nodes/" + node.id)}
                    >
                      {node.name}
                    </button>
                    <div className="mono muted">{node.endpoint}</div>
                    {node.maintenance_note ? (
                      <div className="muted">维护：{node.maintenance_note}</div>
                    ) : null}
                  </td>
                  <td>
                    <StatusBadge status={node.status} />
                    {node.resource_is_stale ? (
                      <div className="muted">数据已过期</div>
                    ) : null}
                  </td>
                  <td>{node.cpu_total ?? "-"}</td>
                  <td>
                    {node.memory_available_mib ?? "-"} /{" "}
                    {node.memory_total_mib ?? "-"} MiB
                  </td>
                  <td>{formatBytes(node.storage_free_bytes)}</td>
                  <td>{formatTime(node.resource_sampled_at)}</td>
                  <td>
                    {node.agent_version || "-"}
                    {node.last_error_message ? (
                      <div className="muted">{node.last_error_code}</div>
                    ) : null}
                  </td>
                  <td className="actions">
                    {canRefresh ? (
                      <button
                        className="action"
                        onClick={() => void refresh(node)}
                      >
                        刷新资源
                      </button>
                    ) : null}
                    {canRegister ? (
                      <button
                        className="action"
                        onClick={() => startEdit(node)}
                      >
                        编辑
                      </button>
                    ) : null}
                    <button
                      className="action"
                      onClick={() => void loadAccess(node)}
                    >
                      授权
                    </button>
                    {canRegister ? (
                      <button
                        className="action danger"
                        onClick={() => void removeNode(node)}
                      >
                        注销
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {accessNode ? (
        <Card title={`节点授权：${accessNode.name}`}>
          <p className="muted">
            无授权记录时全部放行；存在记录后非管理员只能访问被授权节点。
          </p>
          {canGrant ? (
            <form
              className="inline"
              onSubmit={(e) => {
                e.preventDefault();
                void grantAccess();
              }}
            >
              <label>
                用户
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
              </label>
              <label>
                权限
                <select
                  value={accessPermission}
                  onChange={(e) => setAccessPermission(e.target.value)}
                >
                  <option value="OPERATE">操作</option>
                  <option value="VIEW">查看</option>
                </select>
              </label>
              <button className="action primary" type="submit">
                授权
              </button>
              <button
                className="action"
                type="button"
                onClick={() => setAccessNode(null)}
              >
                关闭
              </button>
            </form>
          ) : (
            <button className="action" onClick={() => setAccessNode(null)}>
              关闭
            </button>
          )}
          {accessRules.length === 0 ? (
            <Empty text="无授权记录（默认全部放行）" />
          ) : (
            <table>
              <thead>
                <tr>
                  <th>用户/组</th>
                  <th>权限</th>
                  <th>创建时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {accessRules.map((rule) => (
                  <tr key={rule.id}>
                    <td>{rule.username || rule.group_name || "-"}</td>
                    <td className="mono">{rule.permission}</td>
                    <td>{formatTime(rule.created_at)}</td>
                    <td>
                      {canGrant ? (
                        <button
                          className="action danger"
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
