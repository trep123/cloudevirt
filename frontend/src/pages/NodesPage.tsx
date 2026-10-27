import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBanner, StatusBadge, describeError, formatBytes, formatTime } from "../components/ui";
import type { Node, NodeAccess } from "../types";

export function NodesPage() {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [accessRules, setAccessRules] = useState<NodeAccess[]>([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [accessUser, setAccessUser] = useState("");
  const [accessPermission, setAccessPermission] = useState("OPERATE");

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

  async function refresh(id: number) {
    try {
      await api.refreshNode(id);
      await reload();
    } catch (err) {
      setError(describeError(err));
    }
  }

  async function showAccess(node: Node) {
    setSelectedNode(node);
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
    if (!selectedNode || !accessUser) return;
    try {
      await api.createNodeAccess({
        node: selectedNode.id,
        user: Number(accessUser),
        permission: accessPermission,
      });
      setAccessUser("");
      const page = await api.nodeAccess(selectedNode.id);
      setAccessRules(page.results);
    } catch (err) {
      setError(describeError(err));
    }
  }

  async function revokeAccess(id: number) {
    try {
      await api.deleteNodeAccess(id);
      if (selectedNode) {
        const page = await api.nodeAccess(selectedNode.id);
        setAccessRules(page.results);
      }
    } catch (err) {
      setError(describeError(err));
    }
  }

  return (
    <>
      <div className="page-head">
        <h2>节点</h2>
        <button className="action" onClick={() => void reload()}>刷新列表</button>
      </div>
      <ErrorBanner message={error} />
      <Card title={`共 ${nodes.length} 个节点`}>
        {loading ? (
          <Empty text="加载中…" />
        ) : nodes.length === 0 ? (
          <Empty text="尚未注册节点，请执行 Agent 部署后再登记。" />
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
                    <strong>{node.name}</strong>
                    <div className="mono muted">{node.endpoint}</div>
                  </td>
                  <td>
                    <StatusBadge status={node.status} />
                    {node.resource_is_stale ? <div className="muted">数据已过期</div> : null}
                  </td>
NaN
                  <td>
                    {node.memory_available_mib ?? "-"} / {node.memory_total_mib ?? "-"} MiB
                  </td>
                  <td>{formatBytes(node.storage_free_bytes)}</td>
                  <td>{formatTime(node.resource_sampled_at)}</td>
                  <td>
                    {node.agent_version || "-"}
                    {node.last_error_message ? (
                      <div className="muted">{node.last_error_code}</div>
                    ) : null}
                  </td>
                  <td>
                    <button className="action" onClick={() => void refresh(node.id)}>刷新资源</button>
                    <button className="action" onClick={() => void showAccess(node)}>授权</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {selectedNode ? (
        <Card title={`节点授权：${selectedNode.name}`}>
          <p className="muted">为用户分配该节点的操作权限。无授权记录时全部放行；存在记录后只有被授权用户可操作。</p>
          <form className="inline" onSubmit={(e) => { e.preventDefault(); void grantAccess(); }}>
            <label>用户 ID<input value={accessUser} onChange={(e) => setAccessUser(e.target.value)} placeholder="用户 ID" required /></label>
            <label>权限<select value={accessPermission} onChange={(e) => setAccessPermission(e.target.value)}><option value="OPERATE">操作</option><option value="VIEW">查看</option></select></label>
            <button className="action primary" type="submit">授权</button>
          </form>
          {accessRules.length === 0 ? <Empty text="无授权记录（默认全部放行）" /> : (
            <table>
              <thead><tr><th>用户/组</th><th>权限</th><th>创建时间</th><th>操作</th></tr></thead>
              <tbody>
                {accessRules.map((r) => (
                  <tr key={r.id}>
                    <td>{r.username || r.group_name || "-"}</td>
                    <td className="mono">{r.permission}</td>
                    <td>{formatTime(r.created_at)}</td>
                    <td><button className="action danger" onClick={() => void revokeAccess(r.id)}>撤销</button></td>
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
