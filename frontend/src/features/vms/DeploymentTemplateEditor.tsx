import { useEffect, useState } from "react";
import { api } from "../../api";
import { Card, ErrorBanner, describeError } from "../../components/ui";
import type { Template, Image } from "../../types";

export function DeploymentTemplateEditor({
  templates,
}: {
  templates: Template[];
}) {
  const [images, setImages] = useState<Image[]>([]),
    [parent, setParent] = useState(""),
    [image, setImage] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null),
    [notice, setNotice] = useState("");
  const [lockCpu, setLockCpu] = useState(false),
    [lockMemory, setLockMemory] = useState(false),
    [start, setStart] = useState(true),
    [autostart, setAutostart] = useState(false);
  useEffect(() => {
    let alive = true;
    api
      .images()
      .then((data) => {
        if (alive) setImages(data.results.filter((i) => i.is_ready));
      })
      .catch((e) => {
        if (alive) setError(describeError(e));
      });
    return () => {
      alive = false;
    };
  }, []);
  async function publish(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      const t = templates.find((t) => t.id === Number(parent));
      if (!t || !image) throw Error("请选择规格模板和可用镜像");
      const configuration = {
        image: Number(image),
        vcpu: t.vcpu,
        memory_mib: t.memory_mib,
        disk_gib: t.disk_gib,
        start_after_create: start,
        autostart,
      };
      const draft = await api.request<{ id: number; version: number }>(
        `/templates/${t.id}/versions`,
        {
          method: "POST",
          body: JSON.stringify({
            configuration,
            constraints: {
              locked: [
                "image",
                ...(lockCpu ? ["vcpu"] : []),
                ...(lockMemory ? ["memory_mib"] : []),
              ],
            },
          }),
        },
      );
      await api.request(`/template-versions/${draft.id}/publish`, {
        method: "POST",
        body: "{}",
      });
      setNotice(
        `已发布 ${t.name} v${draft.version}；发布版本保持不变，后续修改将创建新版本。`,
      );
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card title="发布部署模板版本">
      <p className="muted">
        将现有规格与镜像固化为可复用版本，继承规格模板可见性。此操作不会创建虚拟机或复制镜像。
      </p>
      <ErrorBanner message={error} />
      {notice && <p>{notice}</p>}
      <form className="inline" onSubmit={publish}>
        <label>
          规格模板
          <select
            value={parent}
            onChange={(e) => setParent(e.target.value)}
            required
          >
            <option value="">选择模板</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          系统镜像
          <select
            value={image}
            onChange={(e) => setImage(e.target.value)}
            required
          >
            <option value="">选择镜像</option>
            {images.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name} · {i.format}
              </option>
            ))}
          </select>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={lockCpu}
            onChange={(e) => setLockCpu(e.target.checked)}
          />
          锁定 CPU
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={lockMemory}
            onChange={(e) => setLockMemory(e.target.checked)}
          />
          锁定内存
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={start}
            onChange={(e) => setStart(e.target.checked)}
          />
          立即启动
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={autostart}
            onChange={(e) => setAutostart(e.target.checked)}
          />
          宿主机重启后自启
        </label>
        <button className="action primary" disabled={busy} type="submit">
          {busy ? "发布中…" : "创建并发布新版本"}
        </button>
      </form>
    </Card>
  );
}
