import RFB from "@novnc/novnc";
import { api, ApiError } from "../../api";

export type DesktopState =
  | "idle"
  | "authorizing"
  | "connecting"
  | "connected"
  | "rendering"
  | "reconnecting"
  | "paused"
  | "failed"
  | "closed";
export type DesktopMetrics = {
  handshakeMs: number | null;
  firstDrawMs: number | null;
  updatesPerSecond: number | null;
  drawMs: number | null;
};
export type DesktopSession = {
  session_id: string;
  path: string;
  password: string;
};
export type DesktopOptions = {
  quality: number;
  compression: number;
  scale: boolean;
  viewOnly: boolean;
};

export class DesktopEngine {
  private client: RFB | null = null;
  private session: string | null = null;
  private generation = 0;
  private disposed = false;
  private stopped = false;
  private retry = 0;
  private retryTimer: ReturnType<typeof setTimeout> | undefined;
  private hiddenTimer: ReturnType<typeof setTimeout> | undefined;
  private heartbeat: ReturnType<typeof setInterval> | undefined;
  private sample: ReturnType<typeof setInterval> | undefined;
  private detach: (() => void)[] = [];
  private options: DesktopOptions = {
    quality: 6,
    compression: 2,
    scale: true,
    viewOnly: false,
  };
  constructor(
    private target: HTMLElement,
    private instance: number,
    private state: (value: DesktopState, message?: string) => void,
    private metrics: (value: DesktopMetrics) => void,
    private clipboard: (text: string) => void,
    private endpoints?: { create: string; lease: string },
  ) {
    window.addEventListener("online", this.online);
    window.addEventListener("offline", this.offline);
    window.addEventListener("blur", this.blur);
    document.addEventListener("visibilitychange", this.visibility);
  }
  private online = () => {
    if (!this.stopped && !this.disposed && !this.client) void this.connect();
  };
  private offline = () => {
    this.release();
    this.state("paused", "网络离线，恢复后重新授权");
  };
  private visibility = () => {
    this.blur();
    clearTimeout(this.hiddenTimer);
    if (document.hidden)
      this.hiddenTimer = setTimeout(() => {
        if (!this.stopped) {
          this.release();
          this.state("paused", "后台会话已暂停");
        }
      }, 30000);
    else if (!this.stopped && !this.disposed && !this.client)
      void this.connect();
  };
  configure(options: DesktopOptions) {
    this.options = options;
    if (this.client) {
      this.client.qualityLevel = options.quality;
      this.client.compressionLevel = options.compression;
      this.client.scaleViewport = options.scale;
      this.client.viewOnly = options.viewOnly;
    }
  }
  start() {
    this.stopped = false;
    this.retry = 0;
    void this.connect();
  }
  private async connect() {
    if (this.disposed || this.stopped || !navigator.onLine || document.hidden)
      return;
    this.release();
    const generation = this.generation,
      started = performance.now();
    this.state("authorizing");
    const current = () =>
      !this.disposed && !this.stopped && generation === this.generation;
    try {
      const session = await api.request<DesktopSession>(
        this.endpoints?.create ||
          `/console/instances/${this.instance}/sessions`,
        { method: "POST" },
      );
      if (!current()) {
        void this.closeSession(session.session_id);
        return;
      }
      this.session = session.session_id;
      this.state("connecting");
      const scheme = location.protocol === "https:" ? "wss:" : "ws:";
      const client = new RFB(
        this.target,
        scheme + "//" + location.host + session.path,
        { credentials: { password: session.password }, shared: true },
      );
      this.client = client;
      this.configure(this.options);
      client.background = "#000";
      let connected = false,
        draws = 0,
        drawTime = 0,
        lastSample = performance.now();
      const values: DesktopMetrics = {
        handshakeMs: null,
        firstDrawMs: null,
        updatesPerSecond: null,
        drawMs: null,
      };
      this.metrics({ ...values });
      const listen = (name: string, fn: (event: Event) => void) => {
        const guarded = (event: Event) => {
          if (current()) fn(event);
        };
        client.addEventListener(name, guarded);
        this.detach.push(() => client.removeEventListener(name, guarded));
      };
      listen("connect", () => {
        connected = true;
        const stable = setTimeout(() => {
          if (current()) this.retry = 0;
        }, 30000);
        this.detach.push(() => clearTimeout(stable));
        values.handshakeMs = performance.now() - started;
        this.state("connected");
        this.metrics({ ...values });
        let renewing = false;
        this.heartbeat = setInterval(async () => {
          if (renewing || !current()) return;
          renewing = true;
          try {
            await api.request(
              `${this.endpoints?.lease || "/console/sessions"}/${session.session_id}`,
              {
                method: "POST",
              },
            );
          } catch (error) {
            if (current()) this.failed(error);
          } finally {
            renewing = false;
          }
        }, 20000);
      });
      listen("disconnect", () => this.failed(new Error("桌面连接已断开")));
      listen("securityfailure", () => {
        this.stopped = true;
        this.release();
        this.state("failed", "VNC 认证失败，请检查节点控制台配置后重连");
      });
      listen("credentialsrequired", () =>
        client.sendCredentials({ password: session.password }),
      );
      listen("clipboard", (event) =>
        this.clipboard(
          ((event as CustomEvent<{ text: string }>).detail?.text || "").slice(
            0,
            65536,
          ),
        ),
      );
      // Instance-only visible canvas instrumentation. No global prototype or RFB protocol patch.
      const canvas = this.target.querySelector("canvas"),
        context = canvas?.getContext("2d");
      if (context) {
        const original = context.drawImage;
        const draw = original.bind(context) as (...args: unknown[]) => void;
        context.drawImage = ((...args: unknown[]) => {
          const begin = performance.now();
          draw(...args);
          if (!current() || !connected) return;
          draws++;
          drawTime += performance.now() - begin;
          if (values.firstDrawMs === null) {
            values.firstDrawMs = performance.now() - started;
            this.state("rendering");
            this.metrics({ ...values });
          }
        }) as typeof context.drawImage;
        this.detach.push(() => {
          context.drawImage = original;
        });
      }
      this.sample = setInterval(() => {
        if (!current() || !connected) return;
        const now = performance.now(),
          seconds = (now - lastSample) / 1000;
        values.updatesPerSecond = draws / seconds;
        values.drawMs = draws ? drawTime / draws : null;
        draws = 0;
        drawTime = 0;
        lastSample = now;
        this.metrics({ ...values });
      }, 2000);
      const timeout = setTimeout(() => {
        if (current() && !connected) this.failed(new Error("桌面握手超时"));
      }, 20000);
      this.detach.push(() => clearTimeout(timeout));
    } catch (error) {
      if (current()) this.failed(error);
    }
  }
  private failed(error: unknown) {
    this.release();
    if (this.disposed || this.stopped) return;
    if (
      error instanceof ApiError &&
      [401, 403, 404, 409].includes(error.status)
    ) {
      this.state("failed", error.message);
      return;
    }
    if (this.retry >= 3) {
      this.state("failed", error instanceof Error ? error.message : "连接失败");
      return;
    }
    this.retry++;
    this.state(
      "reconnecting",
      `连接中断，${2 ** this.retry} 秒后重新授权（${this.retry}/3）`,
    );
    this.retryTimer = setTimeout(
      () => void this.connect(),
      1000 * 2 ** this.retry,
    );
  }
  private closeSession(id: string) {
    return api
      .request(`${this.endpoints?.lease || "/console/sessions"}/${id}`, {
        method: "DELETE",
        keepalive: true,
      })
      .catch(() => undefined);
  }
  private release() {
    this.generation++;
    clearTimeout(this.retryTimer);
    clearInterval(this.heartbeat);
    clearInterval(this.sample);
    this.detach.splice(0).forEach((fn) => fn());
    this.client?.blur();
    this.client?.disconnect();
    this.client = null;
    if (this.session) {
      void this.closeSession(this.session);
      this.session = null;
    }
    this.target.replaceChildren();
  }
  focus() {
    this.client?.focus({ preventScroll: true });
  }
  blur = () => {
    this.client?.blur();
  };
  paste(text: string) {
    if (text.length <= 65536) this.client?.clipboardPasteFrom(text);
  }
  ctrlAltDel() {
    this.client?.sendCtrlAltDel();
  }
  stop() {
    this.stopped = true;
    this.release();
    this.state("closed");
  }
  dispose() {
    this.disposed = true;
    this.stopped = true;
    this.release();
    clearTimeout(this.hiddenTimer);
    window.removeEventListener("online", this.online);
    window.removeEventListener("offline", this.offline);
    window.removeEventListener("blur", this.blur);
    document.removeEventListener("visibilitychange", this.visibility);
  }
}
