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

export function VncConsole({ instanceId }: { instanceId: number }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<Status>("connecting");
  const [message, setMessage] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let client: RFB | null = null;
    const container = containerRef.current;

    setStatus("connecting");
    setMessage(null);

    api.instanceConsole(instanceId)
      .then((info) => {
        if (cancelled || !container) return;
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        const url = `${protocol}://${window.location.host}${info.path}`;
        client = new RFB(container, url, {
          credentials: { password: info.password },
          shared: true,
        });
        client.scaleViewport = true;
        client.viewOnly = false;
        client.background = "#000";
        client.addEventListener("connect", () => {
          setStatus("connected");
          setMessage(null);
        });
        client.addEventListener("disconnect", () => {
          setStatus("disconnected");
        });
        client.addEventListener("securityfailure", () => {
          setStatus("error");
          setMessage("VNC 认证失败，请重新打开控制台。");
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus("error");
        setMessage(describeError(err));
      });

    return () => {
      cancelled = true;
      if (client) {
        client.disconnect();
      }
      if (container) {
        container.innerHTML = "";
      }
    };
  }, [instanceId, attempt]);

  return (
    <div className="vnc-panel">
      <div className="vnc-toolbar">
        <span className={`vnc-status vnc-${status}`}>{STATUS_LABEL[status]}</span>
        <button className="action" type="button" onClick={() => setAttempt((value) => value + 1)}>
          重新连接
        </button>
      </div>
      <div className="vnc-screen" ref={containerRef} />
      {message ? <div className="banner banner-error">{message}</div> : null}
    </div>
  );
}
