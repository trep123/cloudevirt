import { useEffect, useRef, useState, type CSSProperties } from "react";
import { ClipboardShortcuts } from "../features/console/ClipboardShortcuts";
import {
  DesktopEngine,
  type DesktopState,
  type DesktopMetrics,
} from "../features/console/DesktopEngine";
import { Icon } from "./icons";

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
  instanceName,
  clipboardConfigured = null,
}: {
  instanceId: number;
  desktopAvailable?: boolean;
  instanceName?: string;
  clipboardConfigured?: boolean | null;
}) {
  const target = useRef<HTMLDivElement>(null),
    engine = useRef<DesktopEngine | null>(null);
  const panel = useRef<HTMLDivElement>(null);
  const [browserFull, setBrowserFull] = useState(false);
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
    const resize = () => {
      if (!panel.current) return;
      const top =
        pageFull || document.fullscreenElement === panel.current
          ? 0
          : Math.max(56, panel.current.getBoundingClientRect().top);
      panel.current.style.setProperty(
        "--console-available-height",
        `${Math.max(380, window.innerHeight - top - 24)}px`,
      );
    };
    const fullscreen = () => {
      setBrowserFull(document.fullscreenElement === panel.current);
      resize();
    };
    resize();
    window.addEventListener("resize", resize);
    document.addEventListener("fullscreenchange", fullscreen);
    return () => {
      window.removeEventListener("resize", resize);
      document.removeEventListener("fullscreenchange", fullscreen);
    };
  }, [pageFull]);
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
    const focusIn = () => setCaptured(true);
    const focusOut = () => setCaptured(false);
    container.addEventListener("focusin", focusIn);
    container.addEventListener("focusout", focusOut);
    container.addEventListener("mousedown", focus);
    window.addEventListener("keydown", shortcut, true);
    window.addEventListener("blur", blur);
    return () => {
      container.removeEventListener("mousedown", focus);
      container.removeEventListener("focusin", focusIn);
      container.removeEventListener("focusout", focusOut);
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
  const connected = ["connected", "rendering"].includes(state);
  const displaySize =
    metrics?.width && metrics?.height
      ? `${metrics.width} × ${metrics.height}`
      : "等待画面";
  return (
    <div
      ref={panel}
      className={`console-workspace console-studio${pageFull ? " console-page-fullscreen" : ""}`}
      style={
        {
          "--vnc-aspect-ratio": `${metrics?.width || 16} / ${metrics?.height || 9}`,
          "--vnc-ratio": (metrics?.width || 16) / (metrics?.height || 9),
        } as CSSProperties
      }
    >
      <header className="console-commandbar">
        <div className="console-identity">
          <span className="console-app-icon">
            <Icon name="console" size={19} />
          </span>
          <div>
            <strong>{instanceName || `虚拟机 #${instanceId}`}</strong>
            <span>
              远程桌面 <i /> noVNC
            </span>
          </div>
        </div>
        <div className="console-command-actions">
          <span
            className={`console-state ${connected ? "is-connected" : state === "failed" ? "is-failed" : ""}`}
            role="status"
          >
            <i />
            {desktopAvailable ? labels[state] : "虚拟机未运行"}
          </span>
          <button
            className={`action sm ${!connected ? "primary" : ""}`}
            disabled={!desktopAvailable}
            onClick={() => engine.current?.start()}
          >
            <Icon name="refresh" size={14} />
            {connected ? "重新连接" : "连接桌面"}
          </button>
          <button
            className="action sm console-icon-button"
            aria-label="断开桌面"
            title="断开桌面"
            disabled={!desktopAvailable || ["closed", "idle"].includes(state)}
            onClick={() => {
              engine.current?.stop();
              setCaptured(false);
            }}
          >
            <Icon name="power" size={15} />
          </button>
          <span className="console-toolbar-divider" />
          <button
            className={`action sm ${connected && !pageFull ? "primary" : ""}`}
            aria-pressed={pageFull}
            onClick={() => setPageFull((v) => !v)}
          >
            <Icon name={pageFull ? "collapse" : "expand"} size={14} />
            {pageFull ? "退出页面全屏" : "页面全屏"}
          </button>
          <button
            className="action sm console-icon-button"
            aria-label={browserFull ? "退出浏览器全屏" : "浏览器全屏"}
            title={browserFull ? "退出浏览器全屏" : "浏览器全屏"}
            aria-pressed={browserFull}
            onClick={() => {
              if (document.fullscreenElement === panel.current)
                void document
                  .exitFullscreen()
                  .catch(() => setMessage("无法退出全屏"));
              else
                void panel.current
                  ?.requestFullscreen()
                  .catch(() => setMessage("浏览器拒绝全屏请求"));
            }}
          >
            <Icon name="external" size={15} />
          </button>
        </div>
      </header>
      <div className="console-settingsbar">
        <div className="console-settings-group">
          <label className="console-quality">
            <Icon name="image" size={14} />
            <span>画质</span>
            <select
              value={profile}
              onChange={(e) => setProfile(e.target.value)}
            >
              <option value="text">文字清晰</option>
              <option value="balanced">平衡</option>
              <option value="bandwidth">低带宽</option>
            </select>
          </label>
          <label className="console-setting-toggle">
            <input
              type="checkbox"
              checked={scale}
              onChange={(e) => setScale(e.target.checked)}
            />
            适应窗口
          </label>
          <label className="console-setting-toggle">
            <input
              type="checkbox"
              checked={viewOnly}
              onChange={(e) => setViewOnly(e.target.checked)}
            />
            <Icon name="key" size={13} />
            本地只读
          </label>
        </div>
        <div className="console-settings-group">
          <span className={`console-capture ${captured ? "is-captured" : ""}`}>
            <Icon name="console" size={13} />
            {viewOnly ? "只读浏览" : captured ? "键鼠已捕获" : "点击画面操作"}
          </span>
          <button
            className="console-key-button"
            onClick={() => {
              engine.current?.blur();
              setCaptured(false);
            }}
            title="释放远程键鼠"
          >
            <kbd>Ctrl</kbd>
            <span>+</span>
            <kbd>Alt</kbd>
            <span className="key-caption">释放</span>
          </button>
          <button
            className="console-key-button"
            disabled={!connected || viewOnly}
            onClick={() => engine.current?.ctrlAltDel()}
            title="向虚拟机发送 Ctrl+Alt+Del"
          >
            <Icon name="menu" size={13} />
            <span>Ctrl+Alt+Del</span>
          </button>
        </div>
      </div>
      {message && (
        <div
          className={`console-feedback ${state === "failed" ? "is-error" : ""}`}
          role="alert"
        >
          <Icon name="info" size={15} />
          {message}
        </div>
      )}
      <div className="console-stage" data-native={!scale}>
        <div className="vnc-viewport">
          <div
            ref={target}
            className="vnc-screen"
            tabIndex={0}
            aria-label="虚拟机远程画面"
          />
        </div>
        {(!desktopAvailable || state !== "rendering") && (
          <div className="console-stage-overlay">
            <span className="console-stage-symbol">
              <Icon
                name={
                  !desktopAvailable
                    ? "power"
                    : state === "failed"
                      ? "alert"
                      : "console"
                }
                size={28}
              />
            </span>
            <strong>
              {!desktopAvailable ? "虚拟机尚未运行" : labels[state]}
            </strong>
            <p>
              {!desktopAvailable
                ? "启动实例后即可建立远程桌面连接"
                : state === "closed"
                  ? "连接已安全释放，可随时重新连接"
                  : state === "paused"
                    ? "返回前台或恢复网络后将重新授权"
                    : "画面通过受授权的控制台会话传输"}
            </p>
            {desktopAvailable && ["failed", "closed"].includes(state) && (
              <button
                className="action primary sm"
                onClick={() => engine.current?.start()}
              >
                <Icon name="refresh" size={14} />
                重新连接
              </button>
            )}
          </div>
        )}
      </div>
      <footer className="console-statusbar">
        <div>
          <span>
            <Icon name="monitor" size={13} />
            {displaySize}
          </span>
          <span className="console-transport">
            VNC · {viewOnly ? "只读" : "交互"}
          </span>
        </div>
        <div>
          <span title="协议握手耗时，不等于实时网络延迟">
            <Icon name="clock" size={13} />
            握手 {value(metrics?.handshakeMs, " ms")}
          </span>
          <span title="实际画面更新次数，不等于视频帧率">
            更新 {value(metrics?.updatesPerSecond, "/s")}
          </span>
          <span
            className={
              clipboardConfigured === false ? "console-clipboard-warning" : ""
            }
            title="双向复制粘贴需要客体剪贴板通道和代理"
          >
            <Icon name="copy" size={13} />
            {clipboardConfigured === false
              ? "剪贴板未配置"
              : clipboardConfigured === true
                ? "剪贴板通道已配置"
                : "剪贴板状态未检测"}
          </span>
        </div>
      </footer>
      <details className="console-help">
        <summary>
          <Icon name="help" size={14} />
          快捷键与连接说明 <Icon name="chevronDown" size={13} />
        </summary>
        <div className="console-help-grid">
          <div>
            <strong>键鼠操作</strong>
            <p>
              点击画面捕获键鼠，<kbd>Ctrl</kbd> + <kbd>Alt</kbd>{" "}
              释放。页面全屏可按 Esc 退出。
            </p>
          </div>
          <div>
            <strong>复制与粘贴</strong>
            <p>
              Ctrl+C / V；Linux 终端用 Ctrl+Shift+C /
              V。仅支持文本，需要客体通道、spice-vdagent
              和浏览器剪贴板写入权限。
              {clipboardConfigured === false
                ? "当前尚未配置，请联系管理员在关机后到硬件页启用。"
                : ""}
            </p>
          </div>
          <div>
            <strong>连接与显示</strong>
            <p>
              后台 30
              秒暂停会话。本地缩放只改变显示比例，实际分辨率由虚拟机输出。
            </p>
          </div>
          <div>
            <strong>绘制指标</strong>
            <p>
              首次画面 {value(metrics?.firstDrawMs, " ms")} · 平均绘制{" "}
              {value(metrics?.drawMs, " ms")}。绘制耗时不含网络耗时。
            </p>
          </div>
        </div>
      </details>
    </div>
  );
}
