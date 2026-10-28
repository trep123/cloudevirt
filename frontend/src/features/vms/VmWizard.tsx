import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { PageHeader } from "../../components/ConsoleUI";
import {
  Card,
  DescList,
  ErrorBanner,
  Field,
  LoadingState,
  Meter,
  describeError,
} from "../../components/ui";
import { Icon } from "../../components/icons";
import type { Image, Node, Network } from "../../types";
const STEPS = ["基本信息", "计算资源", "存储", "网络", "确认"];
type Quota = {
  enforced: boolean;
  limits: Record<string, number>;
  used: Record<string, number>;
};
export function VmWizard({
  onCreated,
  onCancel,
}: {
  onCreated: (id: string) => void;
  onCancel: () => void;
}) {
  const [step, setStep] = useState(0),
    [images, setImages] = useState<Image[]>([]),
    [nodes, setNodes] = useState<Node[]>([]),
    [networks, setNetworks] = useState<Network[]>([]),
    [error, setError] = useState<string | null>(null),
    [ready, setReady] = useState(false),
    [busy, setBusy] = useState(false);
  const [name, setName] = useState(""),
    [image, setImage] = useState(""),
    [node, setNode] = useState(""),
    [cpu, setCpu] = useState(2),
    [memory, setMemory] = useState(2),
    [disk, setDisk] = useState(20),
    [network, setNetwork] = useState("");
  const [quota, setQuota] = useState<Quota | null>(null);
  useEffect(() => {
    let alive = true;
    api
      .request<Quota>("/console/quota")
      .then((q) => {
        if (alive) setQuota(q);
      })
      .catch((e) => {
        if (alive) setError(describeError(e));
      });
    return () => {
      alive = false;
    };
  }, []);
  const key = useRef(crypto.randomUUID()),
    submitting = useRef(false);
  useEffect(() => {
    let alive = true;
    Promise.all([api.images(), api.nodes(), api.networks()])
      .then(([i, n, w]) => {
        if (alive) {
          setImages(i.results.filter((v) => v.is_ready));
          setNodes(n.results.filter((v) => v.is_schedulable));
          setNetworks(w.results.filter((v) => v.is_usable));
          setReady(true);
        }
      })
      .catch((e) => {
        if (alive) setError(describeError(e));
      });
    return () => {
      alive = false;
    };
  }, []);
  function next() {
    if (
      step === 0 &&
      (!/^[A-Za-z0-9][A-Za-z0-9-]{1,62}[A-Za-z0-9]$/.test(name) || !image)
    ) {
      setError("请选择镜像，并填写 3–64 位字母、数字或连字符名称。");
      return;
    }
    if (
      step === 1 &&
      (!node ||
        !Number.isInteger(cpu) ||
        cpu < 1 ||
        cpu > 64 ||
        !Number.isFinite(memory) ||
        memory < 0.125 ||
        memory > 128)
    ) {
      setError("请选择节点，vCPU 为 1–64，内存为 0.125–128 GB。");
      return;
    }
    if (step === 2 && (!Number.isInteger(disk) || disk < 1 || disk > 2048)) {
      setError("系统盘容量须为 1–2048 GB 的整数。");
      return;
    }
    setError(null);
    setStep(step + 1);
  }
  async function submit() {
    if (submitting.current) return;
    if (quota?.enforced) {
      const requested: Record<string, number> = {
        instances: 1,
        vcpu: cpu,
        memory_mib: Math.round(memory * 1024),
        disk_gib: disk,
      };
      if (
        Object.entries(requested).some(
          ([key, value]) => quota.used[key] + value > quota.limits[key],
        )
      ) {
        setError("当前配置超过账号剩余配额，请调整资源规格。");
        return;
      }
    }
    submitting.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await api.createInstance(
        {
          name,
          image: Number(image),
          node: Number(node),
          vcpu: cpu,
          memory_mib: Math.round(memory * 1024),
          disk_gib: disk,
          network_name: network,
          autostart: true,
        },
        key.current,
      );
      onCreated(result.task.id);
    } catch (e) {
      setError(
        describeError(e) +
          "。请求结果不确定时，请先在任务中心核对；同一向导会保留幂等键。",
      );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  const DESCS = [
    "为虚拟机命名并选择已审核的操作系统镜像。",
    "选择目标宿主节点并分配 vCPU 与内存。",
    "配置系统盘容量，磁盘由节点存储目录承载。",
    "选择要接入的虚拟网络。",
    "核对配置，确认后将以异步任务提交到节点。",
  ];
  const selectedImage = images.find((i) => String(i.id) === image);
  const selectedNode = nodes.find((n) => String(n.id) === node);
  const quotaRows: [string, string, number, number, (v: number) => string][] =
    quota?.enforced
      ? [
          ["实例", "instances", 1, 1, (v) => `${v} 台`],
          ["vCPU", "vcpu", cpu, 1, (v) => `${v} 核`],
          ["内存", "memory_mib", Math.round(memory * 1024), 1024, (v) => `${(v / 1024).toFixed(v % 1024 ? 1 : 0)} GB`],
          ["磁盘", "disk_gib", disk, 1, (v) => `${v} GB`],
        ]
      : [];
  return (
    <>
      <PageHeader
        back={{ label: "虚拟机列表", onClick: onCancel }}
        title="创建虚拟机"
        description="配置将由后端校验并通过异步任务提交到节点"
      />
      <div className="wizard-layout">
        <div className="wizard card">
          <ol className="wizard-steps">
            {STEPS.map((s, i) => (
              <li
                className={i === step ? "active" : i < step ? "complete" : ""}
                key={s}
              >
                <span>{i < step ? <Icon name="check" size={13} strokeWidth={2.5} /> : i + 1}</span>
                {s}
              </li>
            ))}
          </ol>
          <div className="wizard-body">
            <h2 className="wizard-section-title">{STEPS[step]}</h2>
            <p className="wizard-section-desc">{DESCS[step]}</p>
            <ErrorBanner message={error} />
            {!ready ? (
              <LoadingState text="正在读取授权镜像、节点和网络…" />
            ) : (
              <div className="wizard-fields">
                {step === 0 ? (
                  <>
                    <Field
                      label="虚拟机名称"
                      hint="3–64 位字母、数字或连字符，首尾须为字母或数字"
                    >
                      <input
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="vm-web-01"
                      />
                    </Field>
                    <Field label="操作系统镜像" hint="仅列出已就绪的镜像">
                      <select
                        value={image}
                        onChange={(e) => {
                          setImage(e.target.value);
                          setNode("");
                        }}
                      >
                        <option value="">选择已审核镜像</option>
                        {images.map((i) => (
                          <option key={i.id} value={i.id}>
                            {i.name} · {i.os_family || i.format}
                            {i.node_name ? ` · ${i.node_name}` : ""}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <p className="muted field-wide">
                      资源归属于当前账号。项目与配额管理尚未启用。
                    </p>
                  </>
                ) : step === 1 ? (
                  <>
                    <Field label="目标节点" hint="仅列出可调度且持有所选镜像的节点">
                      <select
                        value={node}
                        onChange={(e) => setNode(e.target.value)}
                      >
                        <option value="">选择可调度节点</option>
                        {nodes
                          .filter((n) => {
                            return (
                              !selectedImage?.node ||
                              selectedImage.node === n.id
                            );
                          })
                          .map((n) => (
                            <option key={n.id} value={n.id}>
                              {n.name}
                            </option>
                          ))}
                      </select>
                    </Field>
                    <div />
                    <Field label="vCPU（核）" hint="1–64">
                      <input
                        type="number"
                        min="1"
                        max="64"
                        value={cpu}
                        onChange={(e) => setCpu(Number(e.target.value))}
                      />
                    </Field>
                    <Field label="内存（GB）" hint="0.125–128，步进 0.125">
                      <input
                        type="number"
                        min="0.125"
                        max="128"
                        step="0.125"
                        value={memory}
                        onChange={(e) => setMemory(Number(e.target.value))}
                      />
                    </Field>
                  </>
                ) : step === 2 ? (
                  <>
                    <Field label="系统盘（GB）" hint="1–2048 的整数">
                      <input
                        type="number"
                        min="1"
                        max="2048"
                        value={disk}
                        onChange={(e) => setDisk(Number(e.target.value))}
                      />
                    </Field>
                    <Field label="磁盘格式">
                      <input disabled value="qcow2" />
                    </Field>
                    <p className="muted field-wide">
                      使用节点已配置的磁盘目录。容量由后端在事务内检查并预留。
                    </p>
                  </>
                ) : step === 3 ? (
                  <>
                    <Field label="虚拟网络">
                      <select
                        value={network}
                        onChange={(e) => setNetwork(e.target.value)}
                      >
                        <option value="">不接入网络</option>
                        {networks.map((n) => (
                          <option key={n.id} value={n.name}>
                            {n.name} · {n.type}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="网卡型号">
                      <input disabled value="virtio" />
                    </Field>
                    <p className="muted field-wide">
                      地址由宿主机实际 DHCP 配置分配，当前不支持静态 IP 配置。
                    </p>
                  </>
                ) : (
                  <div className="field-wide">
                    <DescList
                      columns={2}
                      items={[
                        ["名称", name],
                        ["镜像", selectedImage?.name],
                        ["节点", selectedNode?.name],
                        ["计算资源", `${cpu} vCPU · ${memory} GB`],
                        ["存储", `${disk} GB · qcow2`],
                        ["网络", network || "不接入"],
                        ["创建行为", "创建后启动，通过任务中心查看进度"],
                      ]}
                    />
                  </div>
                )}
              </div>
            )}
          </div>
          <footer>
            <span className="wizard-footer-hint">
              第 {step + 1} / {STEPS.length} 步
            </span>
            <button className="action" disabled={busy} onClick={onCancel}>
              取消创建
            </button>
            <button
              className="action"
              disabled={step === 0 || busy}
              onClick={() => setStep(step - 1)}
            >
              上一步
            </button>
            {step < 4 ? (
              <button
                className="action primary"
                disabled={!ready || busy}
                onClick={next}
              >
                下一步
              </button>
            ) : (
              <button
                className="action primary"
                disabled={busy}
                onClick={() => void submit()}
              >
                {busy ? "正在提交…" : "确认创建"}
              </button>
            )}
          </footer>
        </div>
        <aside className="wizard-summary">
          <Card title="配置摘要">
            <DescList
              columns={1}
              items={[
                ["名称", name || "—"],
                ["镜像", selectedImage?.name || "—"],
                ["节点", selectedNode?.name || "—"],
                ["规格", `${cpu} vCPU · ${memory} GB`],
                ["系统盘", `${disk} GB · qcow2`],
                ["网络", network || "不接入"],
              ]}
            />
          </Card>
          {quota?.enforced ? (
            <Card title="账号配额" description="已用 + 本次申请 / 上限">
              {quotaRows.map(([label, key, req, , fmt]) => {
                const used = quota.used[key] ?? 0,
                  limit = quota.limits[key] ?? 0,
                  after = used + req,
                  pct = limit ? Math.round((after / limit) * 100) : 0;
                return (
                  <div className="quota-row" key={key}>
                    <span>{label}</span>
                    <span className="quota-head">
                      <span className="muted">剩余 {fmt(Math.max(0, limit - used))}</span>
                      <b className={after > limit ? "danger-text" : ""}>
                        {fmt(after)} / {fmt(limit)}
                      </b>
                    </span>
                    <Meter value={pct} />
                  </div>
                );
              })}
            </Card>
          ) : null}
        </aside>
      </div>
    </>
  );
}
