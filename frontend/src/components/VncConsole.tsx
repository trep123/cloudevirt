import { useEffect, useRef, useState } from "react";

import RFB from "@novnc/novnc";

import { api } from "../api";
import { describeError } from "./ui";

type Status = "connecting" | "connected" | "disconnected" | "error";

const STATUS_LABEL: Record<Status, string> = {
  connecting: "连接中…",
  connected: "已连接",
  disconnected: "连接已断开",
  error: "连接失败",
};

/** 复制文本；非 HTTPS 环境回退到 execCommand。 */
async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // 回退到 execCommand
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  const ok = document.execCommand("copy");
  document.body.removeChild(area);
  return ok;
}

export function VncConsole({ instanceId }: { instanceId: number }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const clientRef = useRef<RFB | null>(null);
  const [status, setStatus] = useState<Status>("connecting");
  const [captured, setCaptured] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [guestClipboard, setGuestClipboard] = useState("");
  const [pasteText, setPasteText] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let client: RFB | null = null;
    let cleanupListeners: (() => void) | null = null;
    const container = containerRef.current;

    setStatus("connecting");
    setCaptured(false);
    setMessage(null);
    setNotice(null);

    api.instanceConsole(instanceId)
      .then((info) => {
        if (cancelled || !container) return;
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        const url = `${protocol}://${window.location.host}${info.path}`;
        client = new RFB(container, url, {
          credentials: { password: info.password },
          shared: true,
        });
        clientRef.current = client;
        client.scaleViewport = true;
        client.viewOnly = false;
        client.background = "#000";

        client.addEventListener("connect", () => {
          setStatus("connected");
          setMessage(null);
          setNotice("点击画面捕获键盘鼠标，按 Ctrl+Alt 释放");
        });
        client.addEventListener("disconnect", () => {
          setStatus("disconnected");
          setCaptured(false);
        });
        client.addEventListener("securityfailure", () => {
          setStatus("error");
          setMessage("VNC 认证失败，请重新打开控制台。");
        });
        client.addEventListener("clipboard", (event) => {
          const text = (event as CustomEvent<{ text: string }>).detail?.text ?? "";
          if (!text) return;
          setGuestClipboard(text);
          void copyText(text);
          setNotice("已接收虚拟机剪贴板内容");
        });

        const focusConsole = () => {
          if (!client) return;
          client.focus({ preventScroll: true });
          setCaptured(true);
          setNotice("键盘鼠标已捕获，按 Ctrl+Alt 释放");
        };

        const releaseConsole = () => {
          if (!client) return;
          client.blur();
          setCaptured(false);
          setNotice("已释放键盘鼠标，点击画面可重新捕获");
        };

        const handlePaste = (event: ClipboardEvent) => {
          if (!client || !container.contains(document.activeElement)) return;
          const text = event.clipboardData?.getData("text/plain") ?? "";
          if (!text) return;
          event.preventDefault();
          client.clipboardPasteFrom(text);
          setNotice("已将剪贴板内容发送到虚拟机");
        };

        const handleShortcut = (event: KeyboardEvent) => {
          if (!container.contains(document.activeElement)) return;
          if (event.ctrlKey && event.altKey && !event.repeat) {
            event.preventDefault();
            event.stopPropagation();
            releaseConsole();
          }
        };

        const handleFocusOut = () => {
          window.setTimeout(() => {
            if (!container.contains(document.activeElement)) {
              setCaptured(false);
            }
          }, 0);
        };

        container.addEventListener("mousedown", focusConsole);
        container.addEventListener("paste", handlePaste);
        container.addEventListener("focusout", handleFocusOut);
        window.addEventListener("keydown", handleShortcut, true);

        cleanupListeners = () => {
          container.removeEventListener("mousedown", focusConsole);
          container.removeEventListener("paste", handlePaste);
          container.removeEventListener("focusout", handleFocusOut);
          window.removeEventListener("keydown", handleShortcut, true);
        };
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus("error");
        setMessage(describeError(err));
      });

    return () => {
      cancelled = true;
      cleanupListeners?.();
      if (client) {
        client.disconnect();
      }
      clientRef.current = null;
      if (container) {
        container.innerHTML = "";
      }
    };
  }, [instanceId, attempt]);

  function sendClipboard() {
    const client = clientRef.current;
    if (!client || !pasteText) return;
    client.clipboardPasteFrom(pasteText);
    setNotice("已将文本发送到虚拟机");
  }

  async function readLocalClipboard() {
    try {
      const text = await navigator.clipboard.readText();
      setPasteText(text);
      setNotice("已读取本机剪贴板");
    } catch {
      setNotice("浏览器未授权读取剪贴板，请手动粘贴到文本框中");
    }
  }

  async function copyGuestClipboard() {
    if (await copyText(guestClipboard)) {
      setNotice("已复制到本机剪贴板");
    } else {
      setNotice("复制失败，请手动选择文本复制");
    }
  }

  function captureMouseKeyboard() {
    const client = clientRef.current;
    if (!client) return;
    client.focus({ preventScroll: true });
    setCaptured(true);
    setNotice("键盘鼠标已捕获，按 Ctrl+Alt 释放");
  }

  function releaseMouseKeyboard() {
    const client = clientRef.current;
    if (!client) return;
    client.blur();
    setCaptured(false);
    setNotice("已释放键盘鼠标，点击画面可重新捕获");
  }

  function sendCtrlAltDel() {
    const client = clientRef.current;
    if (!client) return;
    client.sendCtrlAltDel();
    setNotice("已发送 Ctrl+Alt+Del");
  }

  return (
    <div className="vnc-panel">
      <div className="vnc-toolbar">
        <span className={`vnc-status vnc-${status}`}>{STATUS_LABEL[status]}</span>
        <span className={`vnc-capture ${captured ? "on" : "off"}`}>
          {captured ? "键鼠已捕获" : "键鼠未捕获"}
        </span>
        <div className="vnc-actions">
          <button className="action" type="button" onClick={captureMouseKeyboard}>捕获键鼠</button>
          <button className="action" type="button" onClick={releaseMouseKeyboard}>Ctrl+Alt 释放</button>
          <button className="action" type="button" onClick={sendCtrlAltDel}>Ctrl+Alt+Del</button>
          <button className="action" type="button" onClick={() => setAttempt((value) => value + 1)}>重新连接</button>
        </div>
      </div>
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      <div className="vnc-screen" ref={containerRef} tabIndex={0} />
      {message ? <div className="banner banner-error">{message}</div> : null}
      <div className="vnc-clipboard">
        <div className="vnc-clipboard-title">剪贴板</div>
        <textarea
          value={pasteText}
          onChange={(event) => setPasteText(event.target.value)}
          placeholder="在本机复制后粘贴到这里，再发送到虚拟机"
          rows={2}
        />
        <div className="vnc-actions">
          <button className="action primary" type="button" disabled={!pasteText} onClick={sendClipboard}>
            发送到虚拟机
          </button>
          <button className="action" type="button" onClick={() => void readLocalClipboard()}>
            读取本机剪贴板
          </button>
        </div>
        {guestClipboard ? (
          <div className="vnc-clipboard-guest">
            <span>虚拟机剪贴板：</span>
            <code>{guestClipboard}</code>
            <button className="action" type="button" onClick={() => void copyGuestClipboard()}>复制</button>
            <button className="action" type="button" onClick={() => setPasteText(guestClipboard)}>填入输入框</button>
          </div>
        ) : null}
        <p className="muted">捕获键鼠后，Ctrl+V 会直接粘贴到虚拟机；Ctrl+Alt 释放回本机。</p>
      </div>
    </div>
  );
}
