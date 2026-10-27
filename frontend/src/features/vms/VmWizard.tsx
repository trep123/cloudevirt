import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { PageHeader } from "../../components/ConsoleUI";
import { ErrorBanner, describeError } from "../../components/ui";
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
  return (
    <>
      <PageHeader
        title="创建虚拟机"
        description="配置将由后端校验并通过异步任务提交到节点"
      >
        <button className="action" disabled={busy} onClick={onCancel}>
          取消创建
        </button>
      </PageHeader>
      <div className="wizard">
        <ol className="wizard-steps">
          {STEPS.map((s, i) => (
            <li
              className={i === step ? "active" : i < step ? "complete" : ""}
              key={s}
            >
              <span>{i + 1}</span>
              {s}
            </li>
          ))}
        </ol>
        <ErrorBanner message={error} />
        {quota?.enforced ? (
          <p className="muted">
            账号剩余配额：{quota.limits.instances - quota.used.instances}{" "}
            台虚拟机 · {quota.limits.vcpu - quota.used.vcpu} vCPU ·{" "}
            {(quota.limits.memory_mib - quota.used.memory_mib) / 1024} GB 内存 ·{" "}
            {quota.limits.disk_gib - quota.used.disk_gib} GB 磁盘
          </p>
        ) : null}
        {!ready ? (
          <p role="status">正在读取授权镜像、节点和网络…</p>
        ) : (
          <div className="wizard-fields">
            {step === 0 ? (
              <>
                <label>
                  虚拟机名称
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="vm-web-01"
                  />
                </label>
                <label>
                  操作系统镜像
                  <select
                    value={image}
                    onChange={(e) => setImage(e.target.value)}
                  >
                    <option value="">选择已审核镜像</option>
                    {images.map((i) => (
                      <option key={i.id} value={i.id}>
                        {i.name} · {i.os_family || i.format}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="muted">
                  资源归属于当前账号。项目与配额管理尚未启用。
                </p>
              </>
            ) : step === 1 ? (
              <>
                <label>
                  目标节点
                  <select
                    value={node}
                    onChange={(e) => setNode(e.target.value)}
                  >
                    <option value="">选择可调度节点</option>
                    {nodes.map((n) => (
                      <option key={n.id} value={n.id}>
                        {n.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  vCPU（核）
                  <input
                    type="number"
                    min="1"
                    max="64"
                    value={cpu}
                    onChange={(e) => setCpu(Number(e.target.value))}
                  />
                </label>
                <label>
                  内存（GB）
                  <input
                    type="number"
                    min="0.125"
                    max="128"
                    step="0.125"
                    value={memory}
                    onChange={(e) => setMemory(Number(e.target.value))}
                  />
                </label>
              </>
            ) : step === 2 ? (
              <>
                <label>
                  系统盘（GB）
                  <input
                    type="number"
                    min="1"
                    max="2048"
                    value={disk}
                    onChange={(e) => setDisk(Number(e.target.value))}
                  />
                </label>
                <label>
                  磁盘格式
                  <input disabled value="qcow2" />
                </label>
                <p className="muted">
                  使用节点已配置的磁盘目录。容量由后端在事务内检查并预留。
                </p>
              </>
            ) : step === 3 ? (
              <>
                <label>
                  虚拟网络
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
                </label>
                <label>
                  网卡型号
                  <input disabled value="virtio" />
                </label>
                <p className="muted">
                  地址由宿主机实际 DHCP 配置分配，当前不支持静态 IP 配置。
                </p>
              </>
            ) : (
              <dl className="info-grid">
                <dt>名称</dt>
                <dd>{name}</dd>
                <dt>镜像</dt>
                <dd>{images.find((i) => String(i.id) === image)?.name}</dd>
                <dt>节点</dt>
                <dd>{nodes.find((n) => String(n.id) === node)?.name}</dd>
                <dt>计算资源</dt>
                <dd>
                  {cpu} vCPU · {memory} GB
                </dd>
                <dt>存储</dt>
                <dd>{disk} GB · qcow2</dd>
                <dt>网络</dt>
                <dd>{network || "不接入"}</dd>
                <dt>创建行为</dt>
                <dd>创建后启动，通过任务中心查看进度</dd>
              </dl>
            )}
          </div>
        )}
        <footer>
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
    </>
  );
}
