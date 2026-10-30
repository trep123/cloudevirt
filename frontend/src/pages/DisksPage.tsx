import { useCallback, useEffect, useState, useRef } from "react";
import {
  PageHeader,
  ConfirmOperationModal,
  TaskProgressDrawer,
} from "../components/ConsoleUI";
import { newRequestId } from "../utils/requestId";
import { Pagination } from "../components/ui";

import { api } from "../api";
import {
  Card,
  Toolbar,
  Empty,
  ErrorBanner,
  StatusBadge,
  describeError,
  formatBytes,
} from "../components/ui";
import type { Disk } from "../types";

export function DisksPage({ embedded = false }: { embedded?: boolean }) {
  const [disks, setDisks] = useState<Disk[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [instanceFilter, setInstanceFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [retained, setRetained] = useState(false),
    [page, setPage] = useState(1),
    [total, setTotal] = useState(0);
  const [deleting, setDeleting] = useState<Disk | null>(null),
    [busy, setBusy] = useState(false),
    [task, setTask] = useState<string | null>(null);
  const key = useRef(""),
    submitting = useRef(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.disks({
        status: statusFilter,
        instance: instanceFilter,
        retained,
        page,
      });
      setDisks(result.results);
      setTotal(result.count);
      setError(null);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }, [statusFilter, instanceFilter, retained, page]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const totalSize = disks.reduce((sum, disk) => sum + (disk.status === "DELETED" ? 0 : disk.size_gib || 0), 0);
  const readyCount = disks.filter((disk) => disk.status === "READY").length;
  const failedCount = disks.filter((disk) => disk.status === "FAILED").length;

  return (
    <>
      {!embedded && <PageHeader title="我的数据卷" description="查看磁盘归属与使用状态，清理保留或已卸载的数据卷" />}
      <Toolbar>
          <label>
            实例 ID
            <input
              type="number"
              min={1}
              value={instanceFilter}
              onChange={(e) => {
                setInstanceFilter(e.target.value);
                setPage(1);
              }}
              placeholder="过滤"
            />
          </label>
          <label>
            状态
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">现有磁盘</option>
              <option value="CREATING">创建中</option>
              <option value="READY">就绪</option>
              <option value="FAILED">失败</option>
              <option value="DETACHED">已卸载</option>
              <option value="DELETED">已删除（历史记录）</option>
            </select>
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={retained}
              onChange={(e) => {
                setRetained(e.target.checked);
                setPage(1);
              }}
            />
            仅保留 / 已卸载磁盘
          </label>
          <button className="action" onClick={() => void reload()}>
            刷新
          </button>
      </Toolbar>
      <ErrorBanner message={error} />
      <div className="banner banner-info">
        默认仅显示现有磁盘；已删除磁盘仅在选择“已删除（历史记录）”时显示，不计入分配容量。虚拟机删除后保留的磁盘、硬件页面卸载的数据盘均可在此清理。删除会永久移除磁盘及其内部快照；使用中或仍有依赖的磁盘由后端拒绝删除。
      </div>
      <Card flush title={`数据卷 · ${total}`} description={`当前页：就绪 ${readyCount} · 失败 ${failedCount} · 分配 ${totalSize} GiB`}>
        {loading ? (
          <Empty text="加载中…" />
        ) : disks.length === 0 ? (
          <Empty text="暂无磁盘" />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
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
                  <th className="col-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                {disks.map((disk) => (
                  <tr key={disk.id}>
                    <td className="mono">{disk.name}</td>
                    <td>
                      {disk.instance_name || `#${disk.instance}`}
                      <div className="muted">
                        {disk.node_name}
                        {disk.instance_deleted ? " · 实例已删除" : ""}
                      </div>
                    </td>
                    <td>{disk.role}</td>
                    <td>
                      <StatusBadge status={disk.status} />
                      {disk.status === "DELETED" && <div className="muted">已清理 · 历史记录</div>}
                      {disk.is_orphan ? (
                        <div className="muted">
                          {disk.instance_deleted
                            ? "删除实例时保留"
                            : "已卸载 / 待清理"}
                        </div>
                      ) : null}
                    </td>
                    <td>{disk.status === "DELETED" ? "—" : `${disk.size_gib} GiB`}</td>
                    <td>{disk.status === "DELETED" ? "—" : formatBytes(disk.virtual_size_bytes)}</td>
                    <td className="mono">{disk.target_dev}</td>
                    <td className="mono muted">{disk.relative_path}</td>
                    <td className="col-actions">
                      <button
                        className="action danger sm"
                        disabled={!disk.can_delete || busy}
                        title={
                          disk.can_delete
                            ? "永久删除保留磁盘"
                            : "使用中的磁盘、已删除磁盘或无权限的资源不可清理"
                        }
                        onClick={() => {
                          key.current = newRequestId();
                          setError(null);
                          setDeleting(disk);
                        }}
                      >
                        删除磁盘
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <Pagination page={page} pageSize={20} total={total} onChange={setPage} />
      {deleting && (
        <ConfirmOperationModal
          target={`${deleting.name} · ${deleting.size_gib} GiB · ${deleting.node_name || ""}`}
          operation="永久删除磁盘"
          description={`将删除 ${deleting.relative_path} 的数据及内部快照，无法恢复。节点会重新检查虚拟机、快照和磁盘依赖；有引用时停止删除。`}
          busy={busy}
          error={error}
          onCancel={() => {
            setDeleting(null);
            setError(null);
          }}
          onConfirm={() => {
            if (submitting.current) return;
            submitting.current = true;
            setBusy(true);
            setError(null);
            void api
              .request<{ task_id: string }>(`/disks/${deleting.id}`, {
                method: "DELETE",
                headers: { "Idempotency-Key": key.current },
              })
              .then((v) => {
                setDeleting(null);
                setTask(v.task_id);
              })
              .catch((e) => setError(describeError(e)))
              .finally(() => {
                submitting.current = false;
                setBusy(false);
              });
          }}
        />
      )}
      {task && (
        <TaskProgressDrawer
          id={task}
          onClose={() => {
            setTask(null);
            void reload();
          }}
        />
      )}
    </>
  );
}
