import { useEffect, useRef, useState } from "react";
import {
  DesktopEngine,
  type DesktopState,
  type DesktopMetrics,
} from "../features/console/DesktopEngine";
import { ErrorBanner } from "./ui";

const labels: Record<DesktopState, string> = {
  idle: "δ����",
  authorizing: "������Ȩ",
  connecting: "Э��������",
  connected: "������ɣ��ȴ�����",
  rendering: "����ʾ����",
  reconnecting: "��������",
  paused: "����ͣ",
  failed: "����ʧ��",
  closed: "�ѹر�",
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
    [profile, setProfile] = useState("text"),
    [scale, setScale] = useState(true),
    [viewOnly, setViewOnly] = useState(false);
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
      resize: false,
    });
  }, [profile, scale, viewOnly, desktopAvailable]);
  const value = (number: number | null | undefined, suffix: string) =>
    number == null ? "��" : number.toFixed(1) + suffix;
  return (
    <div className="console-workspace">
      <div className="vnc-toolbar workspace-toolbar">
        <strong>�����Զ�̿���̨</strong>
      </div>
      <div className="console-panes">
        <section className="vnc-panel" aria-label="Զ������">
          <div className="vnc-toolbar">
            <span role="status">
              {desktopAvailable ? labels[state] : "�����δ���У����治������"}
            </span>
            <span>{captured ? "�����Ѳ���" : "����δ����"}</span>
            <button
              className="action"
              disabled={!desktopAvailable}
              onClick={() => engine.current?.start()}
            >
              ������Ȩ����
            </button>
            <button
              className="action"
              onClick={() => {
                engine.current?.stop();
                setCaptured(false);
              }}
            >
              �Ͽ�����
            </button>
            <button
              className="action"
              onClick={() => {
                engine.current?.blur();
                setCaptured(false);
              }}
            >
              Ctrl+Alt �ͷ�
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
                  .catch(() => setMessage("������ܾ�ȫ������"))
              }
            >
              ����ȫ��
            </button>
          </div>
          <div className="vnc-toolbar">
            <label>
              ����{" "}
              <select
                value={profile}
                onChange={(e) => setProfile(e.target.value)}
              >
                <option value="balanced">ƽ��</option>
                <option value="bandwidth">�ʹ���</option>
                <option value="text">��������</option>
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={scale}
                onChange={(e) => setScale(e.target.checked)}
              />
              ���ػ�������
            </label>
            <label>
              <input
                type="checkbox"
                checked={viewOnly}
                onChange={(e) => setViewOnly(e.target.checked)}
              />
              ����ֻ��ģʽ
            </label>
          </div>
          <ErrorBanner message={message} />
          <div className="vnc-viewport">
            <div ref={target} className="vnc-screen" tabIndex={0} />
          </div>
          <p className="muted">
            ʵ�ʻ��棺
            {metrics?.width && metrics?.height
              ? `${metrics.width} �� ${metrics.height}`
              : "�ȴ�����"}
            ����������ֻ�ı���ʾ������������Կ���������ʾ�ߴ����ڡ�Ӳ����ҳ���ã�����ֱ��ʿ��ڿ���ϵͳ����ʾ���á���ѡ��
          </p>
          <div className="console-metrics">
            <span>���� {value(metrics?.handshakeMs, " ms")}</span>
            <span>�״� Canvas ���� {value(metrics?.firstDrawMs, " ms")}</span>
            <span>������� {value(metrics?.updatesPerSecond, "/s")}</span>
            <span>ƽ�����Ƶ��� {value(metrics?.drawMs, " ms")}</span>
          </div>
          <p className="muted">
            ������沶�����Ctrl+Alt �ͷš���̨ 30
            �����ͣ���档���´���Ϊ��Ļˢ�´��������ƺ�ʱ�����������ʱ��
          </p>
          <details>
            <summary>�����壨���ֶ����� / ���ƣ�</summary>
            <textarea
              aria-label="���͵���������ı�"
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
              �����ı�
            </button>
            <textarea
              aria-label="�����������"
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
                  .catch(() => setMessage("����ʧ�ܣ����ֶ�ѡ���ı�"))
              }
            >
              ���Ƶ�����
            </button>
          </details>
        </section>
      </div>
    </div>
  );
}
