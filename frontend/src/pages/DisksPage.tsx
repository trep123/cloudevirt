import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBanner, StatusBadge, describeError } from "../components/ui";
import type { Disk } from "../types";

export function DisksPage() {
  const [disks, setDisks] = useState<Disk[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");

  const reload = useCallback(async () => {
    try {
      const page = await api.disks(statusFilter);
      setDisks(page.results);
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }, [statusFilter]);

  useEffect(() => { void reload(); }, [reload]);

  return (
    <>
      <div className="page-head">
        <h2>磁盘与卷</h2>
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
      <ErrorBanner message={error} />
      <Card title={`共 ${disks.length} 个磁盘`}>
        {disks.length === 0 ? <Empty text="暂无磁盘" /> : (
          <table>
            <thead><tr><th>文件名</th><th>角色</th><th>状态</th><th>容量</th><th>总线</th><th>实例</th></tr></thead>
            <tbody>
              {disks.map((d) => (
                <tr key={d.id}>
                  <td className="mono">{d.name}</td>
                  <td>{d.role}</td>
                  <td><StatusBadge status={d.status} /></td>
                  <td>{d.size_gib} GiB</td>
                  <td className="mono">{d.target_dev}</td>
                  <td className="muted">#{d.instance}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
