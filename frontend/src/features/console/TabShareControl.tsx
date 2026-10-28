import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { describeError } from "../../components/ui";

type Publisher = {
  stream: MediaStream;
  peer: RTCPeerConnection | null;
  requestId: string;
  timer?: ReturnType<typeof setInterval>;
};

export function TabShareControl() {
  const [state, setState] = useState<"idle" | "starting" | "live" | "stopping">(
    "idle",
  );
  const [message, setMessage] = useState(""),
    [link, setLink] = useState("");
  const current = useRef<Publisher | null>(null),
    generation = useRef(0),
    mounted = useRef(true);
  const leasePath = (id: string) => `/console/tab-shares/requests/${id}`;
  async function release(report = false) {
    ++generation.current;
    const publisher = current.current;
    current.current = null;
    if (publisher) {
      clearInterval(publisher.timer);
      publisher.stream.getTracks().forEach((track) => track.stop());
      publisher.peer?.close();
    }
    if (mounted.current) {
      setState("stopping");
      setLink("");
    }
    try {
      if (publisher)
        await api.request(leasePath(publisher.requestId), {
          method: "DELETE",
          keepalive: true,
        });
      if (report && mounted.current) setMessage("页面共享已停止");
    } catch {
      if (report && mounted.current)
        setMessage("本地共享已停止，服务器将在发布租约到期后回收连接");
    } finally {
      if (mounted.current) setState("idle");
    }
  }
  useEffect(() => {
    mounted.current = true;
    const close = () => {
      void release();
    };
    window.addEventListener("pagehide", close);
    return () => {
      mounted.current = false;
      window.removeEventListener("pagehide", close);
      void release();
    };
  }, []);

  async function start() {
    if (state !== "idle") return;
    if (!navigator.mediaDevices?.getDisplayMedia) {
      setMessage(
        "当前浏览器无法共享标签页。请使用支持屏幕共享的浏览器，并通过受信任的 HTTPS 地址访问。",
      );
      return;
    }
    if (typeof globalThis.RTCPeerConnection !== "function") {
      setMessage(
        "浏览器的 WebRTC 接口不可用，请检查 WebRTC 屏蔽或隐私防护设置。",
      );
      return;
    }
    const version = ++generation.current;
    setState("starting");
    setMessage("");
    let stream: MediaStream | null = null;
    try {
      // Capture must be requested directly from this click, before awaiting an API call.
      stream = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: { ideal: 15, max: 30 } },
        audio: false,
        preferCurrentTab: true,
        selfBrowserSurface: "include",
      } as DisplayMediaStreamOptions);
      if (version !== generation.current || !mounted.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const track = stream.getVideoTracks()[0];
      if (
        !track ||
        (track.getSettings().displaySurface &&
          track.getSettings().displaySurface !== "browser")
      )
        throw new Error(
          "请选择浏览器的当前平台标签页，不要选择整个屏幕或窗口。",
        );
      const publisher: Publisher = {
        stream,
        peer: null,
        requestId: crypto.randomUUID(),
      };
      current.current = publisher;
      track.addEventListener(
        "ended",
        () => {
          if (current.current === publisher) void release(true);
        },
        { once: true },
      );
      const fresh = await api.request<{ ice_servers: RTCIceServer[] }>(
        "/console/tab-shares",
      );
      if (version !== generation.current) return;
      const peer = new RTCPeerConnection({ iceServers: fresh.ice_servers });
      publisher.peer = peer;
      peer.addTransceiver(track, { direction: "sendonly", streams: [stream] });
      peer.onconnectionstatechange = () => {
        if (current.current !== publisher) return;
        if (peer.connectionState === "connected") setState("live");
        else if (
          peer.connectionState === "failed" ||
          peer.connectionState === "closed"
        ) {
          setMessage("发布连接已断开，请重新开启共享");
          void release();
        }
      };
      await peer.setLocalDescription(await peer.createOffer());
      await new Promise<void>((resolve, reject) => {
        if (peer.iceGatheringState === "complete") {
          resolve();
          return;
        }
        const done = () => {
          if (peer.iceGatheringState === "complete") finish();
        };
        const finish = (error?: Error) => {
          clearTimeout(timer);
          peer.removeEventListener("icegatheringstatechange", done);
          error ? reject(error) : resolve();
        };
        const timer = setTimeout(
          () => finish(new Error("发布网络协商超时，请检查 ICE/TURN 配置")),
          10000,
        );
        peer.addEventListener("icegatheringstatechange", done);
      });
      if (version !== generation.current) return;
      const result = await api.request<{ sdp: string; watch_path: string }>(
        "/console/tab-shares",
        {
          method: "POST",
          body: JSON.stringify({
            sdp: peer.localDescription?.sdp,
            request_id: publisher.requestId,
            expires_hours: 12,
          }),
        },
      );
      if (version !== generation.current) {
        void api
          .request(leasePath(publisher.requestId), {
            method: "DELETE",
            keepalive: true,
          })
          .catch(() => undefined);
        return;
      }
      await peer.setRemoteDescription({ type: "answer", sdp: result.sdp });
      setLink(new URL(result.watch_path, location.origin).href);
      setMessage(
        "正在共享所选标签页；观看者只读。关闭页面、刷新或停止共享后，串流结束。",
      );
      let renewing = false;
      publisher.timer = setInterval(async () => {
        if (renewing || current.current !== publisher) return;
        renewing = true;
        try {
          await api.request(leasePath(publisher.requestId), { method: "POST" });
        } catch (error) {
          if (current.current === publisher) {
            setMessage(describeError(error));
            void release();
          }
        } finally {
          renewing = false;
        }
      }, 20000);
    } catch (error) {
      stream?.getTracks().forEach((track) => track.stop());
      if (version === generation.current && mounted.current) {
        setMessage(
          error instanceof DOMException && error.name === "NotAllowedError"
            ? "已取消或未允许标签页共享"
            : describeError(error),
        );
        void release();
      }
    }
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setMessage("观看链接已复制，持有链接的人可只读观看");
    } catch {
      setMessage("无法自动复制，请从下方链接框手动复制");
    }
  }
  return (
    <div style={{ position: "relative" }}>
      <div style={{ display: "flex", gap: 8 }}>
        {state === "idle" ? (
          <button className="action" onClick={() => void start()}>
            开启页面共享
          </button>
        ) : (
          <>
            <span
              role="status"
              style={{ alignSelf: "center", color: "var(--primary)" }}
            >
              {state === "live"
                ? "页面共享中"
                : state === "stopping"
                  ? "正在停止"
                  : "正在连接"}
            </span>
            {link && (
              <button className="action" onClick={() => void copy()}>
                复制观看链接
              </button>
            )}
            <button
              className="action danger"
              disabled={state === "stopping"}
              onClick={() => void release(true)}
            >
              停止共享
            </button>
          </>
        )}
      </div>
      {message && (
        <div
          role="status"
          className="card"
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 8px)",
            width: "min(360px, 80vw)",
            zIndex: 100,
            padding: 16,
          }}
        >
          <p>{message}</p>
          {link && (
            <input
              aria-label="页面只读观看链接"
              readOnly
              value={link}
              onFocus={(event) => event.target.select()}
              style={{ width: "100%" }}
            />
          )}
          <button className="action" onClick={() => setMessage("")}>
            收起
          </button>
        </div>
      )}
    </div>
  );
}
