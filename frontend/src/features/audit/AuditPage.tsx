import { useEffect, useState } from "react";
import { api } from "../../api";
import { PageHeader } from "../../components/ConsoleUI";
import {
  Card,
  ErrorBanner,
  describeError,
  formatTime,
  StatusBadge,
} from "../../components/ui";
import type { Paginated } from "../../types";
type Event = {
  id: number;
  actor_username: string;
  action: string;
  target_type: string;
  target_id: string;
  result: string;
  request_id: string;
  created_at: string;
};
export function AuditPage() {
  const [items, setItems] = useState<Event[]>([]),
    [page, setPage] = useState(1),
    [count, setCount] = useState(0),
    [error, setError] = useState<string | null>(null),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .request<Paginated<Event>>("/console/audit?page=" + page)
      .then((p) => {
        if (alive) {
          setItems(p.results);
          setCount(p.count);
          setError(null);
        }
      })
      .catch((e) => {
        if (alive) setError(describeError(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [page]);
  return (
    <>
      <PageHeader
        title="操作与审计日志"
        description="服务端记录的资源操作和认证事件"
      />
      <ErrorBanner message={error} />
      <Card title={`共 ${count} 条记录`}>
        {loading ? <p role="status">正在读取审计日志…</p> : null}
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>账号</th>
              <th>操作</th>
              <th>资源</th>
              <th>结果</th>
              <th>Request ID</th>
            </tr>
          </thead>
          <tbody>
            {items.map((e) => (
              <tr key={e.id}>
                <td>{formatTime(e.created_at)}</td>
                <td>{e.actor_username}</td>
                <td>{e.action}</td>
                <td>
                  {e.target_type}:{e.target_id}
                </td>
                <td>
                  <StatusBadge status={e.result} />
                </td>
                <td className="mono">{e.request_id || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && !items.length ? (
          <p className="empty">暂无操作记录</p>
        ) : null}
        <footer className="pagination">
          <button
            className="action"
            disabled={page === 1}
            onClick={() => setPage(page - 1)}
          >
            上一页
          </button>
          <span>{page}</span>
          <button
            className="action"
            disabled={page * 20 >= count}
            onClick={() => setPage(page + 1)}
          >
            下一页
          </button>
        </footer>
      </Card>
    </>
  );
}
