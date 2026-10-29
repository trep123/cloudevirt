import { useEffect, useState } from "react";
import { api } from "../../api";
import { ErrorBanner, describeError } from "../../components/ui";
import { TaskProgressDrawer } from "../../components/ConsoleUI";

type Display = { model: string; width: number; height: number };
type Info = { configured: Display; video_models: string[] };
export function DisplayPanel({
  id,
  admin,
  stopped,
}: {
  id: number;
  admin: boolean;
  stopped: boolean;
}) {
  const [info, setInfo] = useState<Info | null>(null),
    [error, setError] = useState<string | null>(null),
    [busy, setBusy] = useState(false);
  const [model, setModel] = useState("vga"),
    [width, setWidth] = useState(1920),
    [height, setHeight] = useState(1080),
    [task, setTask] = useState<string | null>(null),
    [showTask, setShowTask] = useState(false),
    [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let alive = true;
    setInfo(null);
    setError(null);
    setTask(null);
    api
      .request<Info>(`/instances/${id}/display`)
      .then((v) => {
        if (alive) {
          setInfo(v);
          setModel(
            v.video_models.includes(v.configured.model)
              ? v.configured.model
              : v.video_models[0] || "vga",
          );
          setWidth(v.configured.width || 1920);
          setHeight(v.configured.height || 1080);
        }
      })
      .catch((e) => {
        if (alive) setError(describeError(e));
      });
    return () => {
      alive = false;
    };
  }, [id, refresh]);
  const save = async () => {
    if (
      !Number.isInteger(width) ||
      !Number.isInteger(height) ||
      width < 640 ||
      width > 3840 ||
      height < 480 ||
      height > 2160
    ) {
      setError("������ 640��480 �� 3840��2160 �������ߴ�");
      return;
    }
    if (
      !window.confirm(
        `���Կ�����Ϊ ${model}��������ʾ�ߴ� ${width}��${height}���´�������Ч������ϵͳ����ʹ���Լ�����ʾ���á�VirtIO ��Ҫ����������ȷ�ϱ��棿`,
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.request<{ task: { id: string } }>(
        `/instances/${id}/display`,
        { method: "POST", body: JSON.stringify({ model, width, height }) },
      );
      setTask(result.task.id);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section>
      <h3>������Կ���������ʾ�ߴ�</h3>
      <ErrorBanner message={error} />
      <button
        type="button"
        onClick={() => setRefresh((v) => v + 1)}
        disabled={busy}
      >
        ˢ���Կ�����
      </button>
      {!info && !error && <p>���ڶ�ȡ�ڵ��Կ����á�</p>}
      {info && (
        <>
          <p>
            ��ǰ���ã�{info.configured.model} ��{" "}
            {info.configured.width
              ? `${info.configured.width} �� ${info.configured.height}`
              : "ϵͳĬ����ʾ�ߴ�"}
          </p>
          <p className="muted">
            �˴��޸������Ӳ����������ҳ���š��ߴ�ͨ�������Կ��ṩ�����壬����ʵ�ʷֱ������ɲ���ϵͳ������������Linux
            ���� VirtIO��Windows
            �л�ǰ�谲װ��Ӧ������������ֶ���������ϵͳ����ʾ���á�ѡ��Ŀ��ֱ��ʣ�noVNC
            ��ʾʵ������ߴ硣
          </p>
          {admin && (
            <div className="infra-form">
              <label>
                �Կ�
                <select
                  value={model}
                  disabled={busy || !stopped || !!task}
                  onChange={(e) => setModel(e.target.value)}
                >
                  {info.video_models.map((v) => (
                    <option key={v} value={v}>
                      {v === "virtio" ? "VirtIO GPU" : "��׼ VGA��64 MiB��"}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                ���óߴ�
                <select
                  defaultValue=""
                  disabled={busy || !stopped || !!task}
                  onChange={(e) => {
                    if (e.target.value) {
                      const [w, h] = e.target.value.split("x").map(Number);
                      setWidth(w);
                      setHeight(h);
                    }
                  }}
                >
                  <option value="">�Զ��� / ѡ��Ԥ��</option>
                  {[
                    "1280x720",
                    "1366x768",
                    "1600x900",
                    "1920x1080",
                    "2560x1440",
                    "3840x2160",
                  ].map((v) => (
                    <option key={v} value={v}>
                      {v.replace("x", " �� ")}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                ����
                <input
                  type="number"
                  min={640}
                  max={3840}
                  value={width}
                  disabled={busy || !stopped || !!task}
                  onChange={(e) => setWidth(Number(e.target.value))}
                />
              </label>
              <label>
                �߶�
                <input
                  type="number"
                  min={480}
                  max={2160}
                  value={height}
                  disabled={busy || !stopped || !!task}
                  onChange={(e) => setHeight(Number(e.target.value))}
                />
              </label>
              <button
                type="button"
                disabled={
                  busy ||
                  !stopped ||
                  !!task ||
                  !info.video_models.includes(model)
                }
                onClick={() => void save()}
              >
                {busy ? "�����ύ��" : "�����������ʾ����"}
              </button>
            </div>
          )}
          {!stopped && (
            <p>
              ���������ر���������ȴ��ڵ�ȷ�Ϻ����޸��Կ����á������Զ��ػ���
            </p>
          )}
        </>
      )}
      {task && (
        <p>
          �����������ύ����δȷ����ɡ�
          <button type="button" onClick={() => setShowTask(true)}>
            �鿴����
          </button>
          ���ɹ���ˢ���Կ����á�
        </p>
      )}
      {task && showTask && (
        <TaskProgressDrawer id={task} onClose={() => setShowTask(false)} />
      )}
    </section>
  );
}
