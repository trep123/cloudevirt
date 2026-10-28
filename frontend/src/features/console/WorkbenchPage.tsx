import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { describeError, ErrorBanner } from "../../components/ui";
import { DesktopEngine } from "./DesktopEngine";

type Workspace = {
  state_fresh: boolean;
  id: string;
  state: string;
  active: boolean;
  stop_complete: boolean;
  error: string;
  expires_at: string | null;
  watch_path?: string;
  broadcast: { state: string; error: string; state_fresh: boolean } | null;
};
const labels: Record<string, string> = {
  QUEUED: "等待创建",
  STARTING: "正在启动",
  READY: "工作台已就绪",
  LIVE: "串流可观看",
  STOPPING: "正在回收资源",
  STOPPED: "已停止",
  ERROR: "运行失败",
};
const base = "/console/workspaces/my";

export function WorkbenchEntry() {
  const [error, setError] = useState("");
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const fragment = location.hash.slice(1);
    history.replaceState(null, "", "/workbench-entry");
    const match = /^([a-f0-9-]{36})\.([A-Za-z0-9_-]{43})$/.exec(fragment);
    if (!match) {
      setError("启动凭证缺失，请从本地页面重新开启工作台。");
      return;
    }
    void (async () => {
      const response = await fetch(
        `/api/v1/console/workspaces/${match[1]}/bootstrap`,
        {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-Workspace-Bootstrap": match[2] },
          signal: AbortSignal.timeout(15000),
        },
      );
      if (!response.ok)
        throw new Error("启动凭证失效，请从本地页面重新开启工作台。");
      const data = await response.json();
      if (
        typeof data.next_path !== "string" ||
        !/^\/(admin|app)\//.test(data.next_path)
      )
        throw new Error("工作台页面无效");
      location.replace(data.next_path);
    })().catch((error) => setError(describeError(error)));
  }, []);
  return (
    <main className="login-screen">
      <div className="login">
        <h1>共享工作台</h1>
        <p role={error ? "alert" : "status"}>
          {error || "正在建立独立的服务端登录会话…"}
        </p>
      </div>
    </main>
  );
}

function WorkbenchControl({ id }: { id: string }) {
  const target = useRef<HTMLDivElement>(null);
  const [message, setMessage] = useState("正在连接");
  useEffect(() => {
    if (!target.current) return;
    const engine = new DesktopEngine(
      target.current,
      0,
      (state, error) =>
        setMessage(
          error ||
            (
              {
                rendering: "已连接，可操作服务端工作台",
                connected: "已连接，等待画面",
              } as Record<string, string>
            )[state] ||
            state,
        ),
      () => {},
      () => {},
      {
        create: `/console/workspaces/${id}/sessions`,
        lease: "/console/workspace-sessions",
      },
    );
    engine.start();
    return () => engine.dispose();
  }, [id]);
  return (
    <section className="card">
      <p role="status">{message}</p>
      <div
        ref={target}
        style={{
          height: "min(65vh, 900px)",
          minHeight: 360,
          background: "#172338",
          overflow: "hidden",
        }}
      />
    </section>
  );
}

export function WorkbenchPage() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null),
    [error, setError] = useState<string | null>(null),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [link, setLink] = useState(""),
    [controlling, setControlling] = useState(false),
    [hours, setHours] = useState(12);
  const mounted = useRef(true),
    requestVersion = useRef(0), mutating = useRef(false);
  useEffect(() => {
    mounted.current = true;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      if (mutating.current) { timer = setTimeout(() => void refresh(), 3000); return; }
      const version = ++requestVersion.current;
      try {
        const result = await api.request<Workspace | null>(base);
        if (!cancelled && version === requestVersion.current) {
          setWorkspace(result);
          setError(null);
        }
      } catch (error) {
        if (!cancelled && version === requestVersion.current)
          setError(describeError(error));
      } finally {
        if (!cancelled) {
          setLoading(false);
          timer = setTimeout(
            () => void refresh(),
            document.hidden ? 15000 : 3000,
          );
        }
      }
    };
    void refresh();
    return () => {
      mounted.current = false;
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);
  async function action(kind: "start" | "stop" | "link") {
    if (busy) return;
    if (
      kind === "stop" &&
      !window.confirm(
        "停止共享工作台？服务端浏览器将关闭，观看链接和控制连接同时失效。",
      )
    )
      return;
    ++requestVersion.current;
    mutating.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await api.request<Workspace & { watch_path?: string }>(
        kind === "link" ? base + "/link" : base,
        {
          method: kind === "stop" ? "DELETE" : "POST",
          body:
            kind === "stop"
              ? undefined
              : JSON.stringify({ expires_hours: hours }),
        },
      );
      if (!mounted.current) return;
      if (kind !== "link") setWorkspace(result);
      if (result.watch_path)
        setLink(new URL(result.watch_path, location.origin).href);
      if (kind === "stop") {
        setLink("");
        setControlling(false);
      }
    } catch (error) {
      if (mounted.current) setError(describeError(error));
    } finally {
      mutating.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return (
    <div className="page-stack">
      <div className="page-heading">
        <div>
          <h1>共享工作台</h1>
          <p className="muted">
            在独立的服务端浏览器操作平台，观看者只读观看整个工作台。关闭本地窗口后继续运行，直到停止或到期。
          </p>
        </div>
      </div>
      {error && <ErrorBanner message={error} />}
      <section className="card">
        {workspace?.active && !workspace.state_fresh && <p role="alert">工作台状态尚未更新，请检查后台任务服务。</p>}
        <h2>
          {loading
            ? "正在读取状态…"
            : labels[workspace?.state || "STOPPED"] || workspace?.state}
        </h2>
        {workspace?.error && <p role="alert">{workspace.error}</p>}
        {workspace?.broadcast && (
          <p>
            串流：
            {labels[workspace.broadcast.state] || workspace.broadcast.state}
            {!workspace.broadcast.state_fresh ? "（状态待刷新）" : ""}{" "}
            {workspace.broadcast.error}
          </p>
        )}
        {workspace?.expires_at && (
          <p>到期时间：{new Date(workspace.expires_at).toLocaleString()}</p>
        )}
        <p className="muted">
          持有分享链接的人能看到工作台内展示的内容；链接不授予平台操作权限。工作台内暂不支持上传本地文件，请在本地平台页面上传。
        </p>
        <div className="toolbar">
          <label>
            有效期{" "}
            <select
              value={hours}
              disabled={busy || workspace?.active}
              onChange={(e) => setHours(Number(e.target.value))}
            >
              {[1, 6, 12, 24].map((value) => (
                <option key={value} value={value}>
                  {value} 小时
                </option>
              ))}
            </select>
          </label>
          {!workspace?.active ? (
            <button
              className="action primary"
              disabled={busy || loading || workspace?.stop_complete === false}
              onClick={() => void action("start")}
            >
              开启工作台
            </button>
          ) : (
            <>
              <button
                className="action"
                disabled={workspace.state !== "READY"}
                onClick={() => setControlling(!controlling)}
              >
                {controlling ? "断开本地控制" : "进入工作台"}
              </button>
              <button
                className="action"
                disabled={busy}
                onClick={() => void action("link")}
              >
                生成新观看链接
              </button>
              <button
                className="action danger"
                disabled={busy}
                onClick={() => void action("stop")}
              >
                停止工作台
              </button>
            </>
          )}
        </div>
        {link && workspace?.active && (
          <div>
            <label>
              只读观看链接（生成新链接后旧链接失效）
              <input
                readOnly
                value={link}
                style={{ width: "100%" }}
                onFocus={(e) => e.target.select()}
              />
            </label>
            <a href={link} target="_blank" rel="noreferrer">
              打开观看页
            </a>
          </div>
        )}
      </section>
      {controlling && workspace?.active && workspace.state === "READY" && (
        <WorkbenchControl id={workspace.id} />
      )}
    </div>
  );
}
