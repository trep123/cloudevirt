import { useEffect, useState } from "react";
import { api } from "../../api";
import { Card, ErrorBanner, describeError } from "../../components/ui";
import type { Template, Image, Node, Network } from "../../types";
import {
  HardwareFields,
  type HardwareConfig,
  type CreationCapabilities,
} from "./HardwareFields";

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
  const [hardware, setHardware] = useState<HardwareConfig>({}),
    [dataDisks, setDataDisks] = useState<number[]>([]),
    [extraNetworks, setExtraNetworks] = useState<string[]>([]),
    [network, setNetwork] = useState(""),
    [networks, setNetworks] = useState<Network[]>([]),
    [nodes, setNodes] = useState<Node[]>([]),
    [node, setNode] = useState(""),
    [caps, setCaps] = useState<CreationCapabilities | null>(null);
  useEffect(() => {
    let alive = true;
    Promise.all([api.nodes(), api.networks()])
      .then(([n, w]) => {
        if (alive) {
          setNodes(n.results);
          setNetworks(w.results.filter((n) => n.is_usable));
        }
      })
      .catch((e) => {
        if (alive) setError(describeError(e));
      });
    return () => {
      alive = false;
    };
  }, []);
  useEffect(() => {
    let alive = true;
    setCaps(null);
    if (node)
      api
        .request<CreationCapabilities>(`/nodes/${node}/capabilities`)
        .then((v) => {
          if (alive) setCaps(v);
        })
        .catch((e) => {
          if (alive) setError(describeError(e));
        });
    return () => {
      alive = false;
    };
  }, [node]);
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
        hardware,
        data_disks: dataDisks,
        additional_networks: extraNetworks,
        network_name: network,
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
                "hardware",
                "data_disks",
                "additional_networks",
                "image",
                ...(lockCpu || hardware.sockets || hardware.cpu_quota_percent
                  ? ["vcpu"]
                  : []),
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
    <Card
      title="发布部署版本"
      description="将规格、镜像与设备配置固化为可交付的版本。"
      className="deployment-editor"
    >
      <div className="deployment-flow">
        <span>
          <b>01</b>关联规格与镜像
        </span>
        <i />
        <span>
          <b>02</b>配置硬件与网络
        </span>
        <i />
        <span>
          <b>03</b>发布版本
        </span>
      </div>
      <p className="muted">
        将现有规格与镜像固化为可复用版本，继承规格模板可见性。此操作不会创建虚拟机或复制镜像。
      </p>
      <ErrorBanner message={error} />
      {notice && <p>{notice}</p>}
      <form className="inline deployment-form" onSubmit={publish}>
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

        <label>
          能力校验节点
          <select value={node} onChange={(e) => setNode(e.target.value)}>
            <option value="">选择节点以编辑高级硬件</option>
            {nodes.map((n) => (
              <option key={n.id} value={n.id}>
                {n.name}
              </option>
            ))}
          </select>
        </label>
        <HardwareFields
          value={hardware}
          onChange={setHardware}
          caps={caps}
          cpu={templates.find((t) => t.id === Number(parent))?.vcpu || 2}
          isAdmin={true}
          locked={!caps}
        />
        <div className="field-wide">
          <h4>数据盘（最多 8 块）</h4>
          {dataDisks.map((size, i) => (
            <label key={i}>
              数据盘 {i + 1}
              <input
                type="number"
                min={1}
                max={2048}
                value={size}
                onChange={(e) =>
                  setDataDisks(
                    dataDisks.map((v, j) =>
                      j === i ? Number(e.target.value) : v,
                    ),
                  )
                }
              />
              <button
                type="button"
                className="action sm"
                onClick={() =>
                  setDataDisks(dataDisks.filter((_, j) => j !== i))
                }
              >
                移除
              </button>
            </label>
          ))}
          <button
            type="button"
            className="action"
            disabled={dataDisks.length >= 8}
            onClick={() => setDataDisks([...dataDisks, 20])}
          >
            添加数据盘
          </button>
        </div>
        <label>
          主网络
          <select
            value={network}
            onChange={(e) => {
              setNetwork(e.target.value);
              setExtraNetworks(
                extraNetworks.filter((n) => n !== e.target.value),
              );
            }}
          >
            <option value="">不接入</option>
            {networks.map((n) => (
              <option key={n.id} value={n.name}>
                {n.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          附加网卡网络（最多 7 个）
          <select
            multiple
            value={extraNetworks}
            onChange={(e) =>
              setExtraNetworks(
                Array.from(e.target.selectedOptions, (o) => o.value),
              )
            }
          >
            {networks
              .filter((n) => n.name !== network)
              .map((n) => (
                <option key={n.id} value={n.name}>
                  {n.name}
                </option>
              ))}
          </select>
        </label>
        <p className="muted field-wide">
          硬件、数据盘、附加网卡在用户部署时固定继承；每台实例生成独立磁盘与
          MAC。模板沿用所属规格的公开 / 用户分配规则。
        </p>
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
