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
      setError("请输入 640×480 至 3840×2160 的整数尺寸");
      return;
    }
    if (
      !window.confirm(
        `将显卡配置为 ${model}，启动显示尺寸 ${width}×${height}。下次启动生效，桌面系统可能使用自己的显示设置。VirtIO 需要客体驱动。确认保存？`,
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
      <h3>虚拟机显卡与启动显示尺寸</h3>
      <ErrorBanner message={error} />
      <button
        type="button"
        onClick={() => setRefresh((v) => v + 1)}
        disabled={busy}
      >
        刷新显卡配置
      </button>
      {!info && !error && <p>正在读取节点显卡配置…</p>}
      {info && (
        <>
          <p>
            当前配置：{info.configured.model} ·{" "}
            {info.configured.width
              ? `${info.configured.width} × ${info.configured.height}`
              : "系统默认显示尺寸"}
          </p>
          <p className="muted">
            此处修改虚拟机硬件，不是网页缩放。尺寸通过虚拟显卡提供给客体，桌面实际分辨率仍由操作系统和驱动决定。Linux
            建议 VirtIO；Windows
            切换前需安装对应驱动。保存后手动启动，在系统“显示设置”选择目标分辨率；noVNC
            显示实际输出尺寸。
          </p>
          {admin && (
            <div className="infra-form">
              <label>
                显卡
                <select
                  value={model}
                  disabled={busy || !stopped || !!task}
                  onChange={(e) => setModel(e.target.value)}
                >
                  {info.video_models.map((v) => (
                    <option key={v} value={v}>
                      {v === "virtio" ? "VirtIO GPU" : "标准 VGA（64 MiB）"}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                常用尺寸
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
                  <option value="">自定义 / 选择预设</option>
                  {[
                    "1280x720",
                    "1366x768",
                    "1600x900",
                    "1920x1080",
                    "2560x1440",
                    "3840x2160",
                  ].map((v) => (
                    <option key={v} value={v}>
                      {v.replace("x", " × ")}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                宽度
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
                高度
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
                {busy ? "正在提交…" : "保存虚拟机显示配置"}
              </button>
            </div>
          )}
          {!stopped && (
            <p>
              请先正常关闭虚拟机，等待节点确认后再修改显卡配置。不会自动关机。
            </p>
          )}
        </>
      )}
      {task && (
        <p>
          配置任务已提交，尚未确认完成。
          <button type="button" onClick={() => setShowTask(true)}>
            查看任务
          </button>
          ；成功后刷新显卡配置。
        </p>
      )}
      {task && showTask && (
        <TaskProgressDrawer id={task} onClose={() => setShowTask(false)} />
      )}
    </section>
  );
}
