import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { ErrorBanner, describeError } from "../../components/ui";
import { MediaEngine, type MediaState, type MediaMetrics } from "./MediaEngine";

type Source = { id: number; name: string; stream_path: string };
const labels: Record<MediaState, string> = {
  idle: "未连接",
  authorizing: "正在授权",
  connecting: "等待媒体和首帧",
  playing: "正在播放",
  degraded: "画面降级",
  reconnecting: "正在重连",
  failed: "连接失败",
  closed: "已停止",
};
export function MediaPanel({ instanceId }: { instanceId: number }) {
  const [sources, setSources] = useState<Source[]>([]),
    [selected, setSelected] = useState("");
  const [ice, setIce] = useState<RTCIceServer[]>([]),
    [manage, setManage] = useState(false);
  const [error, setError] = useState<string | null>(null),
    [message, setMessage] = useState("");
  const [state, setState] = useState<MediaState>("idle"),
    [metrics, setMetrics] = useState<MediaMetrics | null>(null);
  const [attempt, setAttempt] = useState(0),
    [running, setRunning] = useState(false);
  const [name, setName] = useState(""),
    [path, setPath] = useState(""),
    [busy, setBusy] = useState(false);
  const [muted, setMuted] = useState(true),
    [remove, setRemove] = useState(false);
  const video = useRef<HTMLVideoElement>(null),
    engine = useRef<MediaEngine | null>(null);
  const loadGeneration = useRef(0);
  async function load() {
    const generation = ++loadGeneration.current;
    try {
      const data = await api.request<{
        results: Source[];
        can_manage: boolean;
        ice_servers: RTCIceServer[];
      }>(`/console/instances/${instanceId}/media-sources`);
      if (generation !== loadGeneration.current) return;
      setSources(data.results);
      setManage(data.can_manage);
      setIce(data.ice_servers);
      setError(null);
      setSelected((old) =>
        data.results.some((s) => String(s.id) === old)
          ? old
          : String(data.results[0]?.id || ""),
      );
    } catch (e) {
      setError(describeError(e));
    }
  }
  useEffect(() => {
    setRunning(false);
    engine.current?.dispose();
    void load();
    return () => {
      loadGeneration.current++;
    };
  }, [instanceId]);
  useEffect(() => {
    if (!running || !selected || !video.current) return;
    const current = new MediaEngine(
      video.current,
      Number(selected),
      ice,
      (value, detail) => {
        setState(value);
        setMessage(detail || "");
      },
      setMetrics,
      async () => {
        const configuration = await api.request<{
          ice_servers: RTCIceServer[];
        }>(`/console/instances/${instanceId}/media-sources`);
        return configuration.ice_servers;
      },
    );
    engine.current = current;
    setMetrics(null);
    current.start();
    return () => {
      current.dispose();
      engine.current = null;
    };
  }, [running, selected, attempt, ice]);
  const number = (value: number | null | undefined, unit: string) =>
    value === null || value === undefined ? "—" : value.toFixed(1) + unit;
  return (
    <section className="media-panel" aria-label="独立视频">
      <div className="vnc-toolbar">
        <strong>独立视频</strong>
        <span role="status">{labels[state]}</span>
        <select
          aria-label="视频源"
          value={selected}
          onChange={(e) => {
            setSelected(e.target.value);
            setRemove(false);
          }}
        >
          {sources.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <button
          className="action"
          disabled={!selected}
          onClick={() => {
            setRunning(true);
            setAttempt((x) => x + 1);
          }}
        >
          播放 / 重连
        </button>
        <button
          className="action"
          onClick={() => {
            engine.current?.stop();
            setRunning(false);
            setState("closed");
          }}
        >
          停止
        </button>
        <button className="action" onClick={() => setMuted((value) => !value)}>
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
      <ErrorBanner message={error} />
      {message ? <p role="status">{message}</p> : null}
      <video
        ref={video}
        muted={muted}
        autoPlay
        playsInline
        controls
        aria-label="授权视频画面"
      />
      {!sources.length ? (
        <p className="empty">
          尚未配置独立视频源。管理员可登记已发布到媒体网关的流；这里不会生成示例画面。
        </p>
      ) : null}
      <div className="console-metrics">
        <span>实际解码 {number(metrics?.fps, " FPS")}</span>
        <span>接收 {number(metrics?.bitrateKbps, " kb/s")}</span>
        <span>累计丢包 {number(metrics?.lossPercent, "%")}</span>
        <span>抖动 {number(metrics?.jitterMs, " ms")}</span>
        <span>平均抖动缓冲 {number(metrics?.bufferMs, " ms")}</span>
      </div>
      <p className="muted">
        这些是接收端统计，不能据此认定真实端到端延迟。视频连接独立于桌面；前往其他页面或关闭工作区时释放资源。
      </p>
      {manage ? (
        <details>
          <summary>配置视频源</summary>
          <form
            className="inline"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError(null);
              try {
                await api.request(
                  `/console/instances/${instanceId}/media-sources`,
                  {
                    method: "POST",
                    body: JSON.stringify({ name, stream_path: path }),
                  },
                );
                setName("");
                setPath("");
                await load();
              } catch (e) {
                setError(describeError(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              显示名称
              <input
                required
                maxLength={64}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              网关流名称
              <input
                required
                pattern="[A-Za-z0-9][A-Za-z0-9_\\-]{0,63}"
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="camera-01"
              />
            </label>
            <button className="action" disabled={busy}>
              登记视频源
            </button>
            <p>
              流名称映射到服务端配置的 WHEP
              网关。摄像头地址、密码和源发布配置由服务器管理。
            </p>
          </form>
          {selected ? (
            <button className="action danger" onClick={() => setRemove(true)}>
              停用当前视频源
            </button>
          ) : null}
          {remove ? (
            <p>
              确认停用当前视频源并断开其观看会话？
              <button
                className="action danger"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await api.request(`/console/media-sources/${selected}`, {
                      method: "DELETE",
                    });
                    setRunning(false);
                    setRemove(false);
                    await load();
                  } catch (e) {
                    setError(describeError(e));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                确认停用
              </button>
              <button className="action" onClick={() => setRemove(false)}>
                取消
              </button>
            </p>
          ) : null}
        </details>
      ) : null}
    </section>
  );
}
