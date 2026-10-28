import { api, ApiError } from "../../api";
export type MediaState =
  | "idle"
  | "authorizing"
  | "connecting"
  | "playing"
  | "paused"
  | "degraded"
  | "reconnecting"
  | "failed"
  | "closed";
export type MediaMetrics = {
  fps: number | null;
  bitrateKbps: number | null;
  lossPercent: number | null;
  jitterMs: number | null;
  bufferMs: number | null;
};
export class MediaEngine {
  private peer: RTCPeerConnection | null = null;
  private session: string | null = null;
  private leaseToken = "";
  private generation = 0;
  private stopped = false;
  private timer: ReturnType<typeof setInterval> | undefined;
  private heartbeat: ReturnType<typeof setInterval> | undefined;
  private retryTimer: ReturnType<typeof setTimeout> | undefined;
  private timeout: ReturnType<typeof setTimeout> | undefined;
  private retries = 0;
  private frameCallback: number | null = null;
  private cancelIce: (() => void) | undefined;
  constructor(
    private video: HTMLVideoElement,
    private source: number,
    private ice: RTCIceServer[],
    private state: (state: MediaState, message?: string) => void,
    private metrics: (value: MediaMetrics) => void,
    private freshIce?: () => Promise<RTCIceServer[]>,
    private access: {
      createPath?: string;
      leasePrefix?: string;
      anonymous?: boolean;
      headers?: Record<string, string>;
    } = {},
  ) {}
  start() {
    this.stopped = false;
    this.retries = 0;
    void this.connect();
  }
  private async connect() {
    this.release();
    if (this.stopped) return;
    const generation = this.generation,
      current = () => generation === this.generation && !this.stopped;
    this.state("authorizing");
    try {
      const ice = this.freshIce ? await this.freshIce() : this.ice;
      if (!current()) return;
      const peer = new RTCPeerConnection({ iceServers: ice });
      this.peer = peer;
      peer.addTransceiver("video", { direction: "recvonly" });
      peer.addTransceiver("audio", { direction: "recvonly" });
      this.timeout = setTimeout(() => {
        if (current()) this.failed(new Error("媒体连接或首帧等待超时"));
      }, 25000);
      let lastFrame = 0,
        lastBytes = 0,
        lastFrames = 0,
        lastTime = 0,
        rendered = false,
        playingSince = 0;
      const visibleFrame = () => {
        if (!current()) return;
        lastFrame = performance.now();
        if (!rendered) {
          rendered = true;
          playingSince = performance.now();
          clearTimeout(this.timeout);
          this.state("playing");
        }
        if (this.video.requestVideoFrameCallback)
          this.frameCallback =
            this.video.requestVideoFrameCallback(visibleFrame);
      };
      peer.ontrack = (event) => {
        if (!current()) {
          event.track.stop();
          return;
        }
        const stream =
          this.video.srcObject instanceof MediaStream
            ? this.video.srcObject
            : new MediaStream();
        stream.addTrack(event.track);
        this.video.srcObject = stream;
        void this.video.play().catch(() => {
          if (current())
            this.state("connecting", "浏览器阻止播放，请点击播放按钮");
        });
        if (
          event.track.kind === "video" &&
          this.video.requestVideoFrameCallback
        )
          this.frameCallback =
            this.video.requestVideoFrameCallback(visibleFrame);
      };
      peer.onconnectionstatechange = () => {
        if (!current()) return;
        if (peer.connectionState === "failed")
          this.failed(new Error("ICE 媒体连接失败"));
        if (peer.connectionState === "disconnected") {
          this.state("degraded", "媒体连接暂时中断");
          clearTimeout(this.timeout);
          this.timeout = setTimeout(() => {
            if (current() && peer.connectionState === "disconnected")
              this.failed(new Error("媒体中断超时"));
          }, 8000);
        }
        if (peer.connectionState === "connected" && rendered)
          clearTimeout(this.timeout);
      };
      this.state("connecting");
      await peer.setLocalDescription(await peer.createOffer());
      await new Promise<void>((resolve, reject) => {
        if (peer.iceGatheringState === "complete") {
          resolve();
          return;
        }
        const done = () => {
          if (peer.iceGatheringState === "complete") {
            clearTimeout(wait);
            peer.removeEventListener("icegatheringstatechange", done);
            resolve();
          }
        };
        const wait = setTimeout(() => {
          peer.removeEventListener("icegatheringstatechange", done);
          reject(new Error("ICE 收集超时"));
        }, 10000);
        peer.addEventListener("icegatheringstatechange", done);
        this.cancelIce = () => {
          clearTimeout(wait);
          peer.removeEventListener("icegatheringstatechange", done);
          reject(new Error("ICE 收集已取消"));
        };
      });
      if (!current()) return;
      const result = await api.request<{
        session_id: string;
        sdp: string;
        lease_token?: string;
      }>(
        this.access.createPath ||
          `/console/media-sources/${this.source}/sessions`,
        {
          anonymous: this.access.anonymous,
          headers: this.access.headers,
          method: "POST",
          body: JSON.stringify({ sdp: peer.localDescription?.sdp }),
        },
      );
      if (!current()) {
        void this.closeSession(result.session_id, result.lease_token);
        return;
      }
      this.session = result.session_id;
      this.leaseToken = result.lease_token || "";
      await peer.setRemoteDescription({ type: "answer", sdp: result.sdp });
      let renewing = false,
        sampling = false;
      this.heartbeat = setInterval(async () => {
        if (!current() || renewing) return;
        renewing = true;
        try {
          await api.request(
            (this.access.leasePrefix || "/console/media-sessions/") +
              result.session_id,
            {
              anonymous: this.access.anonymous,
              headers: this.leaseToken
                ? { "X-Media-Session-Token": this.leaseToken }
                : {},
              method: "POST",
            },
          );
        } catch (error) {
          if (current()) this.failed(error);
        } finally {
          renewing = false;
        }
      }, 20000);
      this.timer = setInterval(async () => {
        if (!current() || sampling) return;
        sampling = true;
        try {
          const reports = await peer.getStats();
          if (!current()) return;
          reports.forEach((report) => {
            if (report.type !== "inbound-rtp" || report.kind !== "video")
              return;
            const data = report as RTCInboundRtpStreamStats;
            const seconds = lastTime ? (data.timestamp - lastTime) / 1000 : 0;
            const fps =
              seconds > 0 && data.framesDecoded !== undefined
                ? (data.framesDecoded - lastFrames) / seconds
                : null;
            if (
              !this.video.requestVideoFrameCallback &&
              fps &&
              this.video.readyState >= 2
            ) {
              visibleFrame();
            }
            const lost = Math.max(0, data.packetsLost || 0),
              received = data.packetsReceived || 0;
            const loss =
              received + lost ? (lost * 100) / (received + lost) : null;
            this.metrics({
              fps,
              bitrateKbps:
                seconds > 0
                  ? (((data.bytesReceived || 0) - lastBytes) * 8) /
                    seconds /
                    1000
                  : null,
              lossPercent: loss,
              jitterMs: data.jitter === undefined ? null : data.jitter * 1000,
              bufferMs: data.jitterBufferEmittedCount
                ? ((data.jitterBufferDelay || 0) * 1000) /
                  data.jitterBufferEmittedCount
                : null,
            });
            lastBytes = data.bytesReceived || 0;
            lastFrames = data.framesDecoded || 0;
            lastTime = data.timestamp;
            if (rendered && performance.now() - playingSince >= 30000)
              this.retries = 0;
            if (this.video.paused) this.state("paused");
            else if (
              (loss !== null && loss > 5) ||
              (lastFrame && performance.now() - lastFrame > 8000)
            )
              this.state("degraded", "丢包较高或持续没有新画面");
            else if (lastFrame) this.state("playing");
          });
        } catch (error) {
          if (current())
            this.state(
              "degraded",
              error instanceof Error ? error.message : "统计暂不可用",
            );
        } finally {
          sampling = false;
        }
      }, 2000);
    } catch (error) {
      if (current()) this.failed(error);
    }
  }
  private failed(error: unknown) {
    this.release();
    if (this.stopped) return;
    if (
      error instanceof ApiError &&
      [401, 403, 404, 409].includes(error.status)
    ) {
      this.state("failed", error.message);
      return;
    }
    if (this.retries >= 3) {
      this.state(
        "failed",
        error instanceof Error ? error.message : "媒体连接失败",
      );
      return;
    }
    this.retries++;
    this.state("reconnecting", `视频重连 ${this.retries}/3`);
    this.retryTimer = setTimeout(
      () => void this.connect(),
      1000 * 2 ** this.retries,
    );
  }
  private closeSession(id: string, token = this.leaseToken) {
    return api
      .request((this.access.leasePrefix || "/console/media-sessions/") + id, {
        anonymous: this.access.anonymous,
        headers: token ? { "X-Media-Session-Token": token } : {},
        method: "DELETE",
        keepalive: true,
      })
      .catch(() => undefined);
  }
  private release() {
    this.cancelIce?.();
    this.cancelIce = undefined;
    this.generation++;
    clearInterval(this.timer);
    clearInterval(this.heartbeat);
    clearTimeout(this.retryTimer);
    clearTimeout(this.timeout);
    if (this.frameCallback !== null)
      this.video.cancelVideoFrameCallback?.(this.frameCallback);
    this.frameCallback = null;
    this.peer?.getReceivers().forEach((receiver) => receiver.track?.stop());
    this.peer?.close();
    this.peer = null;
    if (this.video.srcObject instanceof MediaStream)
      this.video.srcObject.getTracks().forEach((track) => track.stop());
    this.video.pause();
    this.video.srcObject = null;
    if (this.session) {
      void this.closeSession(this.session);
      this.session = null;
      this.leaseToken = "";
    }
  }
  stop() {
    this.stopped = true;
    this.release();
    this.state("closed");
  }
  dispose() {
    this.stopped = true;
    this.release();
  }
}
