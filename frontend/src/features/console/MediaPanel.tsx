import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { ErrorBanner, describeError } from "../../components/ui";

type Source = { id: number; name: string; stream_path: string };
type Broadcast = {
  id: string;
  kind: "desktop" | "source";
  name: string;
  source_id: number;
  active: boolean;
  state: string;
  state_fresh: boolean;
  stop_complete: boolean;
  error: string;
  link_expires_at: string | null;
  updated_at: string;
  watch_path?: string;
};
const labels: Record<string, string> = {
  QUEUED: "等待发布任务",
  STARTING: "正在采集 / 编码",
  LIVE: "串流可观看",
  WAITING: "等待视频源",
  STOPPING: "正在停止",
  STOPPED: "已停止",
  ERROR: "发布失败",
};
export function MediaPanel({ instanceId }: { instanceId: number }) {
  const [sources, setSources] = useState<Source[]>([]),
    [broadcasts, setBroadcasts] = useState<Broadcast[]>([]);
  const [selected, setSelected] = useState(""),
    [hours, setHours] = useState(12),
    [links, setLinks] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null),
    [manage, setManage] = useState(false);
  const [name, setName] = useState(""),
    [path, setPath] = useState("");
  const generation = useRef(0);
  const [removing, setRemoving] = useState<number | null>(null);
  useEffect(() => {
    const current = ++generation.current;
    setLinks({});
    setBusy(false);
    setError(null);
    setBroadcasts([]);
    setSources([]);
    const load = async () => {
      try {
        const [rows, options] = await Promise.all([
          api.request<{ results: Broadcast[] }>(
            `/console/instances/${instanceId}/broadcasts`,
          ),
          api.request<{ results: Source[]; can_manage: boolean }>(
            `/console/instances/${instanceId}/media-sources`,
          ),
        ]);
        if (generation.current !== current) return;
        setBroadcasts(rows.results);
        setSources(options.results);
        setManage(options.can_manage);
        setSelected((old) =>
          options.results.some((source) => String(source.id) === old)
            ? old
            : String(options.results[0]?.id || ""),
        );
      } catch (e) {
        if (generation.current === current) setError(describeError(e));
      }
    };
    void load();
    const timer = setInterval(() => {
      if (!document.hidden) void load();
    }, 5000);
    return () => {
      generation.current++;
      clearInterval(timer);
    };
  }, [instanceId]);
  async function action(route: string, method: string, body?: object) {
    const current = generation.current;
    setBusy(true);
    setError(null);
    try {
      const row = await api.request<Broadcast>(route, {
        method,
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if (generation.current !== current) return;
      setBroadcasts((old) => [
        row,
        ...old.filter((item) => item.id !== row.id),
      ]);
      if (row.watch_path)
        setLinks((old) => ({
          ...old,
          [row.id]: location.origin + row.watch_path,
        }));
      if (!row.active) setLinks((old) => ({ ...old, [row.id]: "" }));
    } catch (e) {
      if (generation.current === current) setError(describeError(e));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }
  const desktop = broadcasts.find((item) => item.kind === "desktop");
  return (
    <section className="media-panel" aria-label="串流发布">
      <h3>串流发布</h3>
      <p>
        这里只开启服务端串流，不在本机播放
        WebRTC。关闭此页面不会停流；到期或点击停止后结束。
      </p>
      <ErrorBanner message={error} />
      <div className="vnc-toolbar">
        <label>
          链接有效期{" "}
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
          >
            {[1, 4, 12, 24].map((value) => (
              <option key={value} value={value}>
                {value} 小时
              </option>
            ))}
          </select>
        </label>
        <button
          className="action primary"
          disabled={busy || desktop?.active || desktop?.stop_complete === false}
          onClick={() =>
            void action(`/console/instances/${instanceId}/broadcasts`, "POST", {
              kind: "desktop",
              expires_hours: hours,
            })
          }
        >
          开启桌面串流
        </button>
      </div>
      <div className="vnc-toolbar">
        <select
          aria-label="独立视频源"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          {sources.map((source) => (
            <option key={source.id} value={source.id}>
              {source.name}
            </option>
          ))}
        </select>
        <button
          className="action"
          disabled={
            busy ||
            !selected ||
            broadcasts.some(
              (item) =>
                item.kind === "source" &&
                item.source_id === Number(selected) &&
                item.active,
            )
          }
          onClick={() =>
            void action(`/console/instances/${instanceId}/broadcasts`, "POST", {
              kind: "source",
              source_id: Number(selected),
              expires_hours: hours,
            })
          }
        >
          开启视频源串流
        </button>
      </div>
      {!sources.length ? (
        <p>
          尚无独立视频源。登记网关流路径后才能开启，实际视频需由服务器采集或发布。
        </p>
      ) : null}
      {broadcasts.map((row) => (
        <article className="broadcast-card" key={row.id}>
          <strong>{row.name}</strong>{" "}
          <span role="status">
            {row.state_fresh
              ? labels[row.state] || row.state
              : "发布状态已过期，请检查后台任务"}
          </span>
          {row.error ? <p>{row.error}</p> : null}
          <p>
            链接到期：
            {row.link_expires_at
              ? new Date(row.link_expires_at).toLocaleString()
              : "—"}{" "}
            · 状态更新：{new Date(row.updated_at).toLocaleTimeString()}
          </p>
          {row.active ? (
            <>
              <p>
                持链接者可匿名观看；观看链接不授予虚拟机管理或键鼠控制权限。
              </p>
              {links[row.id] ? (
                <>
                  <input
                    aria-label={row.name + " 观看链接"}
                    readOnly
                    value={links[row.id]}
                    onFocus={(e) => e.target.select()}
                  />
                  <button
                    className="action"
                    onClick={() => {
                      if (!navigator.clipboard) {
                        setError("请选中链接手动复制");
                        return;
                      }
                      void navigator.clipboard
                        .writeText(links[row.id])
                        .catch(() => setError("复制失败，请选择链接手动复制"));
                    }}
                  >
                    复制观看链接
                  </button>
                </>
              ) : (
                <p>链接凭证仅在生成时显示。需要再次分享时，请重新生成。</p>
              )}
              <button
                className="action"
                disabled={busy}
                onClick={() =>
                  void action(`/console/broadcasts/${row.id}`, "POST", {
                    expires_hours: hours,
                  })
                }
              >
                重新生成链接并撤销旧链接
              </button>
              <button
                className="action danger"
                disabled={busy}
                onClick={() =>
                  void action(`/console/broadcasts/${row.id}`, "DELETE")
                }
              >
                停止串流
              </button>
            </>
          ) : null}
        </article>
      ))}
      {manage ? (
        <details>
          <summary>登记独立视频源</summary>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError(null);
              const current = generation.current;
              try {
                const source = await api.request<Source>(
                  `/console/instances/${instanceId}/media-sources`,
                  {
                    method: "POST",
                    body: JSON.stringify({ name, stream_path: path }),
                  },
                );
                if (current !== generation.current) return;
                setSources((old) => [...old, source]);
                setSelected(String(source.id));
                setName("");
                setPath("");
              } catch (e) {
                if (current === generation.current) setError(describeError(e));
              } finally {
                if (current === generation.current) setBusy(false);
              }
            }}
          >
            <label>
              名称
              <input
                required
                maxLength={64}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              网关流路径
              <input
                required
                pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,63}"
                value={path}
                onChange={(e) => setPath(e.target.value)}
              />
            </label>
            <button className="action" disabled={busy}>
              登记视频源
            </button>
            <p>源地址和发布凭据仅在服务器配置。</p>
          </form>
          <ul>
            {sources.map((source) => (
              <li key={source.id}>
                {source.name}{" "}
                <button
                  className="action danger"
                  disabled={busy}
                  onClick={() => setRemoving(source.id)}
                >
                  停用视频源
                </button>
                {removing === source.id ? (
                  <span>
                    确认停用 {source.name} 并关闭关联观看会话？
                    <button
                      className="action danger"
                      disabled={busy}
                      onClick={async () => {
                        const current = generation.current;
                        setBusy(true);
                        setError(null);
                        try {
                          await api.request(
                            `/console/media-sources/${source.id}`,
                            { method: "DELETE" },
                          );
                          if (current === generation.current) {
                            setSources((old) =>
                              old.filter((item) => item.id !== source.id),
                            );
                            setSelected("");
                            setRemoving(null);
                          }
                        } catch (e) {
                          if (current === generation.current)
                            setError(describeError(e));
                        } finally {
                          if (current === generation.current) setBusy(false);
                        }
                      }}
                    >
                      确认停用
                    </button>
                    <button
                      className="action"
                      onClick={() => setRemoving(null)}
                    >
                      取消
                    </button>
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
