import { useEffect, useRef, useState } from "react";
import {
  DesktopEngine,
  type DesktopState,
  type DesktopMetrics,
} from "../features/console/DesktopEngine";
import { MediaPanel } from "../features/console/MediaPanel";
import { ErrorBanner } from "./ui";

const labels: Record<DesktopState, string> = {
  idle: "未连接",
  authorizing: "正在授权",
  connecting: "协议连接中",
  connected: "握手完成，等待画面",
  rendering: "已显示画面",
  reconnecting: "正在重连",
  paused: "已暂停",
  failed: "连接失败",
  closed: "已关闭",
};
export function VncConsole({
  instanceId,
  desktopAvailable = true,
}: {
  instanceId: number;
  desktopAvailable?: boolean;
}) {
  const target = useRef<HTMLDivElement>(null),
    engine = useRef<DesktopEngine | null>(null);
  const [state, setState] = useState<DesktopState>("idle"),
    [message, setMessage] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<DesktopMetrics | null>(null),
    [clipboard, setClipboard] = useState(""),
    [paste, setPaste] = useState("");
  const [captured, setCaptured] = useState(false),
    [profile, setProfile] = useState("balanced"),
    [scale, setScale] = useState(true),
    [viewOnly, setViewOnly] = useState(false);
  const [layout, setLayout] = useState("split");
  useEffect(() => {
    if (!target.current || !desktopAvailable) return;
    const current = new DesktopEngine(
      target.current,
      instanceId,
      (value, detail) => {
        setState(value);
        setMessage(detail || null);
        if (!["rendering", "connected"].includes(value)) setCaptured(false);
      },
      setMetrics,
      setClipboard,
    );
    engine.current = current;
    current.start();
    const container = target.current;
    const focus = () => {
      current.focus();
      setCaptured(true);
    };
    const shortcut = (event: KeyboardEvent) => {
      if (
        container.contains(document.activeElement) &&
        event.ctrlKey &&
        event.altKey
      ) {
        event.preventDefault();
        event.stopPropagation();
        current.blur();
        setCaptured(false);
      }
    };
    const blur = () => setCaptured(false);
    container.addEventListener("mousedown", focus);
    window.addEventListener("keydown", shortcut, true);
    window.addEventListener("blur", blur);
    return () => {
      container.removeEventListener("mousedown", focus);
      window.removeEventListener("keydown", shortcut, true);
      window.removeEventListener("blur", blur);
      current.dispose();
      engine.current = null;
    };
  }, [instanceId, desktopAvailable]);
  useEffect(() => {
    const values =
      profile === "bandwidth" ? [3, 6] : profile === "text" ? [9, 2] : [6, 2];
    engine.current?.configure({
      quality: values[0],
      compression: values[1],
      scale,
      viewOnly,
    });
  }, [profile, scale, viewOnly, desktopAvailable]);
  const value = (number: number | null | undefined, suffix: string) =>
    number == null ? "—" : number.toFixed(1) + suffix;
  return (
    <div className={"console-workspace layout-" + layout}>
      <div className="vnc-toolbar workspace-toolbar">
        <strong>桌面与视频工作区</strong>
        <label>
          布局{" "}
          <select value={layout} onChange={(e) => setLayout(e.target.value)}>
            <option value="split">左右分屏</option>
            <option value="stack">上下排列</option>
          </select>
        </label>
      </div>
      <div className="console-panes">
        <section className="vnc-panel" aria-label="远程桌面">
          <div className="vnc-toolbar">
            <span role="status">
              {desktopAvailable ? labels[state] : "虚拟机未运行，桌面不可连接"}
            </span>
            <span>{captured ? "键鼠已捕获" : "键鼠未捕获"}</span>
            <button
              className="action"
              disabled={!desktopAvailable}
              onClick={() => engine.current?.start()}
            >
              重新授权连接
            </button>
            <button
              className="action"
              onClick={() => {
                engine.current?.stop();
                setCaptured(false);
              }}
            >
              断开桌面
            </button>
            <button
              className="action"
              onClick={() => {
                engine.current?.blur();
                setCaptured(false);
              }}
            >
              Ctrl+Alt 释放
            </button>
            <button
              className="action"
              disabled={!["connected", "rendering"].includes(state)}
              onClick={() => engine.current?.ctrlAltDel()}
            >
              Ctrl+Alt+Del
            </button>
            <button
              className="action"
              onClick={() =>
                void target.current
                  ?.requestFullscreen()
                  .catch(() => setMessage("浏览器拒绝全屏请求"))
              }
            >
              桌面全屏
            </button>
          </div>
          <div className="vnc-toolbar">
            <label>
              画质{" "}
              <select
                value={profile}
                onChange={(e) => setProfile(e.target.value)}
              >
                <option value="balanced">平衡</option>
                <option value="bandwidth">低带宽</option>
                <option value="text">文字清晰</option>
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={scale}
                onChange={(e) => setScale(e.target.checked)}
              />
              适应窗口
            </label>
            <label>
              <input
                type="checkbox"
                checked={viewOnly}
                onChange={(e) => setViewOnly(e.target.checked)}
              />
              本地只读模式
            </label>
          </div>
          <ErrorBanner message={message} />
          <div ref={target} className="vnc-screen" tabIndex={0} />
          <div className="console-metrics">
            <span>握手 {value(metrics?.handshakeMs, " ms")}</span>
            <span>首次 Canvas 绘制 {value(metrics?.firstDrawMs, " ms")}</span>
            <span>画面更新 {value(metrics?.updatesPerSecond, "/s")}</span>
            <span>平均绘制调用 {value(metrics?.drawMs, " ms")}</span>
          </div>
          <p className="muted">
            点击桌面捕获键鼠，Ctrl+Alt 释放。后台 30
            秒后暂停桌面。更新次数不是视频 FPS，绘制耗时不是端到端延迟。
          </p>
          <details>
            <summary>剪贴板（仅手动发送 / 复制）</summary>
            <textarea
              aria-label="发送到虚拟机的文本"
              maxLength={65536}
              value={paste}
              onChange={(e) => setPaste(e.target.value)}
              rows={2}
            />
            <button
              className="action"
              disabled={!paste || viewOnly}
              onClick={() => engine.current?.paste(paste)}
            >
              发送文本
            </button>
            <textarea
              aria-label="虚拟机剪贴板"
              value={clipboard}
              readOnly
              rows={2}
            />
            <button
              className="action"
              disabled={!clipboard}
              onClick={() =>
                void navigator.clipboard
                  ?.writeText(clipboard)
                  .catch(() => setMessage("复制失败，请手动选择文本"))
              }
            >
              复制到本机
            </button>
          </details>
        </section>
        <MediaPanel instanceId={instanceId} />
      </div>
    </div>
  );
}
