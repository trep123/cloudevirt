import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBanner, StatusBadge, describeError, formatBytes } from "../components/ui";
import type { Disk } from "../types";

export function DisksPage() {
  const [disks, setDisks] = useState<Disk[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [instanceFilter, setInstanceFilter] = useState("");
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setDisks((await api.disks({ status: statusFilter, instance: instanceFilter })).results);
      setError(null);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }, [statusFilter, instanceFilter]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const totalSize = disks.reduce((sum, disk) => sum + (disk.size_gib || 0), 0);
  const readyCount = disks.filter((disk) => disk.status === "READY").length;
  const failedCount = disks.filter((disk) => disk.status === "FAILED").length;

  return (
    <>
      <div className="page-head">
        <h2>磁盘与卷</h2>
        <div className="actions">
          <label>实例 ID
            <input type="number" min={1} value={instanceFilter} onChange={(e) => setInstanceFilter(e.target.value)} placeholder="过滤" />
          </label>
          <label>状态
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">全部</option>
              <option value="CREATING">创建中</option>
              <option value="READY">就绪</option>
              <option value="FAILED">失败</option>
              <option value="DELETED">已删除</option>
            </select>
          </label>
          <button className="action" onClick={() => void reload()}>刷新</button>
        </div>
      </div>
      <ErrorBanner message={error} />
      <div className="banner banner-info">
        磁盘清单为只读视图。删除磁盘文件请在虚拟机页面删除实例时选择清理磁盘。
      </div>
      <Card title="磁盘概况">
        <div className="stats">
          <div className="stat"><span>磁盘总数</span><strong>{disks.length}</strong></div>
          <div className="stat"><span>就绪</span><strong>{readyCount}</strong></div>
          <div className="stat"><span>失败</span><strong>{failedCount}</strong></div>
          <div className="stat"><span>分配容量</span><strong>{totalSize} GiB</strong></div>
        </div>
      </Card>
      <Card title={`共 ${disks.length} 个磁盘`}>
        {loading ? <Empty text="加载中…" /> : disks.length === 0 ? <Empty text="暂无磁盘" /> : (
          <table>
            <thead>
              <tr>
                <th>文件名</th>
                <th>所属实例</th>
                <th>角色</th>
                <th>状态</th>
                <th>容量</th>
                <th>虚拟容量</th>
                <th>设备</th>
                <th>路径</th>
              </tr>
            </thead>
            <tbody>
              {disks.map((disk) => (
                <tr key={disk.id}>
                  <td className="mono">{disk.name}</td>
                  <td>{disk.instance_name || `#${disk.instance}`}</td>
                  <td>{disk.role}</td>
                  <td>
                    <StatusBadge status={disk.status} />
                    {disk.is_orphan ? <div className="muted">孤儿文件</div> : null}
                  </td>
                  <td>{disk.size_gib} GiB</td>
                  <td>{formatBytes(disk.virtual_size_bytes)}</td>
                  <td className="mono">{disk.target_dev}</td>
                  <td className="mono muted">{disk.relative_path}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
