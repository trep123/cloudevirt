import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBanner, StatusBadge, describeError, formatBytes, formatTime } from "../components/ui";
import type { Node } from "../types";

export function NodesPage() {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
                    <button className="action" onClick={() => void refresh(node.id)}>
                      刷新资源
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
