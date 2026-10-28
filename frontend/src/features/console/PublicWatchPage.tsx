import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { ErrorBanner, describeError } from "../../components/ui";
import { MediaEngine, type MediaMetrics, type MediaState } from "./MediaEngine";
export function parseWatchGrant(fragment: string) {
  const match =
    /^#?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.([A-Za-z0-9_-]{43})$/.exec(
      fragment,
    );
  return match ? { id: match[1], token: match[2] } : null;
}
type Info = {
  name: string;
  state: string;
  expires_at: string;
  ice_servers: RTCIceServer[];
  can_connect: boolean;
};
const labels: Record<MediaState, string> = {
  idle: "等待串流",
  authorizing: "正在授权",
  connecting: "等待首帧",
  playing: "正在观看",
  paused: "已暂停",
  degraded: "画面降级",
  reconnecting: "正在重连",
  failed: "观看失败",
  closed: "已停止",
};
export function PublicWatchPage() {
  const [grant, setGrant] = useState(() => parseWatchGrant(location.hash)),
    [info, setInfo] = useState<Info | null>(null);
  const [playing, setPlaying] = useState(true),
    [attempt, setAttempt] = useState(0),
    [muted, setMuted] = useState(true);
  const [state, setState] = useState<MediaState>("idle"),
    [error, setError] = useState<string | null>(null),
    [message, setMessage] = useState("");
  const [metrics, setMetrics] = useState<MediaMetrics | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const change = () => {
      setGrant(parseWatchGrant(location.hash));
      setInfo(null);
      setPlaying(true);
      setError(null);
    };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  const id = grant?.id,
    token = grant?.token;
  useEffect(() => {
    if (!id || !token) return;
    let alive = true;
    let loading = false;
    const load = async () => {
      if (loading) return;
      loading = true;
      try {
        const value = await api.request<Info>(
          `/console/broadcasts/${id}/watch`,
          { anonymous: true, headers: { "X-Stream-Token": token } },
        );
        if (alive) {
          setInfo(value);
          setError(null);
        }
      } catch (e) {
        if (alive) {
          setError(describeError(e));
          setInfo(null);
        }
      } finally {
        loading = false;
      }
    };
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [id, token, attempt]);
  const ready = info?.can_connect === true;
  useEffect(() => {
    if (!id || !token || !ready || !playing || !video.current) return;
    const current = new MediaEngine(
      video.current,
      0,
      [],
      (value, detail) => {
        setState(value);
        setMessage(detail || "");
      },
      setMetrics,
      async () =>
        (
          await api.request<Info>(`/console/broadcasts/${id}/watch`, {
            anonymous: true,
            headers: { "X-Stream-Token": token },
          })
        ).ice_servers,
      {
        anonymous: true,
        createPath: `/console/broadcasts/${id}/watch`,
        leasePrefix: "/console/watch-sessions/",
        headers: { "X-Stream-Token": token },
      },
    );
    setMetrics(null);
    current.start();
    return () => current.dispose();
  }, [id, token, ready, playing, attempt]);
  const number = (value: number | null | undefined, unit: string) =>
    value == null ? "—" : value.toFixed(1) + unit;
  return (
    <main className="public-watch">
      <section className="card">
        <h1>{info?.name || "串流观看"}</h1>
        {!grant ? (
          <p role="alert">观看链接不完整，请使用发布者提供的完整链接。</p>
        ) : null}
        <ErrorBanner message={error} />
        {info && !ready ? (
          <p role="status">串流正在准备，请等待发布端就绪。</p>
        ) : null}
        <div className="vnc-toolbar">
          <span role="status">{playing ? labels[state] : "已停止"}</span>
          <button
            className="action primary"
            disabled={!grant}
            onClick={() => {
              setPlaying(true);
              setAttempt((old) => old + 1);
            }}
          >
            重新连接
          </button>
          <button
            className="action"
            onClick={() => {
              setPlaying(false);
              setState("closed");
            }}
          >
            停止观看
          </button>
          <button
            className="action"
            onClick={() => setMuted((value) => !value)}
          >
            {muted ? "开启声音" : "静音"}
          </button>
          <button
            className="action"
            onClick={() =>
              void video.current
                ?.requestFullscreen()
                .catch(() => setMessage("浏览器拒绝全屏请求"))
            }
          >
            全屏
          </button>
        </div>
        {message ? <p role="status">{message}</p> : null}
        <video
          ref={video}
          autoPlay
          playsInline
          muted={muted}
          controls
          aria-label="串流画面"
        />
        <div className="console-metrics">
          <span>实际解码 {number(metrics?.fps, " FPS")}</span>
          <span>接收 {number(metrics?.bitrateKbps, " kb/s")}</span>
          <span>累计丢包 {number(metrics?.lossPercent, "%")}</span>
          <span>抖动 {number(metrics?.jitterMs, " ms")}</span>
        </div>
        <p>
          仅观看，不提供键鼠控制或虚拟机管理权限。
          {info
            ? "链接到期：" + new Date(info.expires_at).toLocaleString()
            : ""}
        </p>
      </section>
    </main>
  );
}
