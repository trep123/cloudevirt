import { useEffect, useRef, useState, type CSSProperties } from "react";
import { ClipboardShortcuts } from "../features/console/ClipboardShortcuts";
import {
  DesktopEngine,
  type DesktopState,
  type DesktopMetrics,
} from "../features/console/DesktopEngine";
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
  const ready = useRef(false),
    readOnly = useRef(false);
  const [pageFull, setPageFull] = useState(false);
  const [state, setState] = useState<DesktopState>("idle"),
    [message, setMessage] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<DesktopMetrics | null>(null);
  const [captured, setCaptured] = useState(false),
    [profile, setProfile] = useState("text"),
    [scale, setScale] = useState(true),
    [viewOnly, setViewOnly] = useState(false);
  readOnly.current = viewOnly;
  useEffect(() => {
    if (!pageFull) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        setPageFull(false);
      }
    };
    window.addEventListener("keydown", escape, true);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", escape, true);
    };
  }, [pageFull]);
  useEffect(() => {
    if (!target.current || !desktopAvailable) return;
    let bridge: ClipboardShortcuts;
    const current = new DesktopEngine(
      target.current,
      instanceId,
      (value, detail) => {
        setState(value);
        ready.current = ["connected", "rendering"].includes(value);
        setMessage(detail || null);
        if (!["rendering", "connected"].includes(value)) setCaptured(false);
      },
      setMetrics,
      (text) => bridge?.receive(text),
    );
    engine.current = current;
    current.start();
    const container = target.current;
    bridge = new ClipboardShortcuts(container, {
      enabled: () => ready.current && !readOnly.current,
      paste: (text) => current.paste(text),
      shortcut: (key, shift) => current.shortcut(key, shift),
      report: setMessage,
    });
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
      bridge.dispose();
      ready.current = false;
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
      resize: false,
    });
  }, [profile, scale, viewOnly, desktopAvailable]);
  const value = (number: number | null | undefined, suffix: string) =>
    number == null ? "—" : number.toFixed(1) + suffix;
  return (
    <div
      className={`console-workspace${pageFull ? " console-page-fullscreen" : ""}`}
      style={
        {
          "--vnc-aspect-ratio": `${metrics?.width || 16} / ${metrics?.height || 9}`,
          "--vnc-ratio": (metrics?.width || 16) / (metrics?.height || 9),
        } as CSSProperties
      }
    >
      <div className="vnc-toolbar workspace-toolbar">
        <strong>虚拟机远程控制台</strong>
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
              aria-pressed={pageFull}
              onClick={() => setPageFull((v) => !v)}
            >
              {pageFull ? "退出页面全屏" : "页面全屏"}
            </button>
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
                void target.current?.parentElement
                  ?.requestFullscreen()
                  .catch(() => setMessage("浏览器拒绝全屏请求"))
              }
            >
              浏览器全屏
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
              本地画面缩放
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
          <div className="vnc-viewport">
            <div ref={target} className="vnc-screen" tabIndex={0} />
          </div>
          <p className="muted">
            实际画面：
            {metrics?.width && metrics?.height
              ? `${metrics.width} × ${metrics.height}`
              : "等待画面"}
            。本地缩放只改变显示比例。虚拟机显卡和启动显示尺寸请在“硬件”页设置；桌面分辨率可在客体系统“显示设置”中选择。
          </p>
          <div className="console-metrics">
            <span>握手 {value(metrics?.handshakeMs, " ms")}</span>
            <span>首次 Canvas 绘制 {value(metrics?.firstDrawMs, " ms")}</span>
            <span>画面更新 {value(metrics?.updatesPerSecond, "/s")}</span>
            <span>平均绘制调用 {value(metrics?.drawMs, " ms")}</span>
          </div>
          <p className="muted">
            点击桌面捕获键鼠，Ctrl+Alt 释放。后台 30
            秒后暂停桌面。更新次数为屏幕刷新次数，绘制耗时不包含网络耗时。
          </p>
          <p className="muted">
            复制 / 粘贴：Ctrl+C / Ctrl+V（macOS 可用 ⌘）；Linux 终端用
            Ctrl+Shift+C / V。仅同步文本，需要客体剪贴板通道和
            spice-vdagent；复制到本机需要浏览器剪贴板写入权限。
          </p>
        </section>
      </div>
    </div>
  );
}
