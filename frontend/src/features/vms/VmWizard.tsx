import { newRequestId } from "../../utils/requestId";
import { useEffect, useRef, useState } from "react";
import { api, fetchAllOptions } from "../../api";
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
import { TemplateDeploymentForm } from "./TemplateDeploymentForm";
import {
  HardwareFields,
  type HardwareConfig,
  type CreationCapabilities,
} from "./HardwareFields";
const STEPS = ["基本信息", "计算资源", "存储", "网络", "确认"];
type Quota = {
  enforced: boolean;
  limits: Record<string, number>;
  used: Record<string, number>;
};
export function VmWizard({
  isAdmin = false,
  onCreated,
  onCancel,
}: {
  isAdmin?: boolean;
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
  const [versions, setVersions] = useState<
      {
        id: number;
        template_name: string;
        version: number;
        configuration: Record<string, unknown>;
        constraints: {
          locked?: string[];
          bounds?: Record<string, { min: number; max: number }>;
        };
      }[]
    >([]),
    [version, setVersion] = useState("");
  const [startAfter, setStartAfter] = useState(true),
    [autostart, setAutostart] = useState(false);
  const [pools, setPools] = useState<
      { id: number; name: string; network: number; enabled: boolean }[]
    >([]),
    [pool, setPool] = useState(""),
    [staticAddress, setStaticAddress] = useState("");
  useEffect(() => {
    let alive = true;
    setPool("");
    const selected = networks.find((n) => n.name === network);
    if (selected)
      void api
        .request<{ results: typeof pools }>(
          `/networks/ip-pools?network=${selected.id}`,
        )
        .then((data) => {
          if (alive) setPools(data.results.filter((p) => p.enabled));
        })
        .catch((e) => {
          if (alive) setError(describeError(e));
        });
    return () => {
      alive = false;
    };
  }, [network, networks]);
  const [caps, setCaps] = useState<CreationCapabilities | null>(null),
    [hardware, setHardware] = useState<HardwareConfig>({}),
    [dataDisks, setDataDisks] = useState<number[]>([]),
    [extraNetworks, setExtraNetworks] = useState<string[]>([]),
    [initialize, setInitialize] = useState(false),
    [hostname, setHostname] = useState(""),
    [guestUser, setGuestUser] = useState("cloudvirt"),
    [sshKeys, setSshKeys] = useState("");
  useEffect(() => {
    let active = true;
    setCaps(null);
    if (node)
      void api
        .request<CreationCapabilities>(`/nodes/${node}/capabilities`)
        .then((value) => {
          if (active) setCaps(value);
        })
        .catch((e) => {
          if (active) setError(describeError(e));
        });
    return () => {
      active = false;
    };
  }, [node]);
  useEffect(() => {
    let active = true;
    Promise.all([
      api.request<{ results: typeof versions }>("/templates/deployments"),
    ])
      .then(([v]) => {
        if (active) {
          setVersions(v.results);
        }
      })
      .catch((e) => {
        if (active) setError(describeError(e));
      });
    return () => {
      active = false;
    };
  }, []);
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
  const key = useRef(newRequestId()),
    submitting = useRef(false);
  useEffect(() => {
    let alive = true;
    Promise.all([
      fetchAllOptions<Image>("/images").then((results) => ({ results })),
      fetchAllOptions<Node>("/nodes").then((results) => ({ results })),
      fetchAllOptions<Network>("/networks").then((results) => ({ results })),
    ])
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
        cpu > cpuLimit ||
        !Number.isFinite(memory) ||
        memory < 0.125 ||
        memory > memoryLimit)
    ) {
      setError("请选择节点，vCPU 为 1–64，内存为 0.125–128 GB。");
      return;
    }
    if (
      step === 2 &&
      (!Number.isInteger(disk) ||
        disk < 1 ||
        disk > diskLimit ||
        dataDisks.some(
          (size) => !Number.isInteger(size) || size < 1 || size > diskLimit,
        ))
    ) {
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
        disk_gib: disk + dataDisks.reduce((total, size) => total + size, 0),
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
      const configuration = {
        ...(pool
          ? {
              static_networks: {
                [network]: {
                  pool: Number(pool),
                  ...(staticAddress ? { address: staticAddress } : {}),
                  default_route: true,
                },
              },
            }
          : {}),
        hardware,
        data_disks: dataDisks,
        additional_networks: extraNetworks,
        ...(initialize
          ? {
              initialization: {
                ...(hostname ? { hostname } : {}),
                username: guestUser,
                ssh_public_keys: sshKeys
                  .split(/\r?\n/)
                  .map((key) => key.trim())
                  .filter(Boolean),
              },
            }
          : {}),
        name,
        image: Number(image),
        node: Number(node),
        vcpu: cpu,
        memory_mib: Math.round(memory * 1024),
        disk_gib: disk,
        network_name: network,
        autostart,
        start_after_create: startAfter,
        ...(version ? { template_version: Number(version) } : {}),
      };
      await api.request("/instances/preflight", {
        method: "POST",
        body: JSON.stringify(configuration),
      });
      const result = await api.createInstance(configuration, key.current);
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
  const selectedVersion = versions.find((v) => v.id === Number(version));
  const locked = new Set(selectedVersion?.constraints.locked || []);
  const cpuLimit = Math.min(
    caps?.policy?.vcpu || 64,
    selectedVersion?.constraints.bounds?.vcpu?.max || 64,
  );
  const memoryLimit =
    Math.min(
      caps?.policy?.memory_mib || 131072,
      selectedVersion?.constraints.bounds?.memory_mib?.max || 131072,
    ) / 1024;
  const diskLimit = Math.min(
    caps?.policy?.disk_gib || 2048,
    selectedVersion?.constraints.bounds?.disk_gib?.max || 2048,
  );
  const quotaRows: [string, string, number, number, (v: number) => string][] =
    quota?.enforced
      ? [
          ["实例", "instances", 1, 1, (v) => `${v} 台`],
          ["vCPU", "vcpu", cpu, 1, (v) => `${v} 核`],
          [
            "内存",
            "memory_mib",
            Math.round(memory * 1024),
            1024,
            (v) => `${(v / 1024).toFixed(v % 1024 ? 1 : 0)} GB`,
          ],
          [
            "磁盘",
            "disk_gib",
            disk + dataDisks.reduce((total, size) => total + size, 0),
            1,
            (v) => `${v} GiB`,
          ],
        ]
      : [];
  if (selectedVersion)
    return (
      <TemplateDeploymentForm
        key={selectedVersion.id}
        version={selectedVersion}
        networks={networks}
        onBack={() => {
          setVersion("");
          setHardware({});
          setDataDisks([]);
          setExtraNetworks([]);
          setNode("");
        }}
        onCancel={onCancel}
        onCreated={onCreated}
      />
    );
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
                <span>
                  {i < step ? (
                    <Icon name="check" size={13} strokeWidth={2.5} />
                  ) : (
                    i + 1
                  )}
                </span>
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
                    <Field label="已发布部署模板">
                      <select
                        value={version}
                        onChange={(e) => {
                          setVersion(e.target.value);
                          setNode("");
                          const v = versions.find(
                            (v) => v.id === Number(e.target.value),
                          );
                          if (v) {
                            const c = v.configuration;
                            if (c.image) setImage(String(c.image));
                            if (c.vcpu) setCpu(Number(c.vcpu));
                            if (c.memory_mib)
                              setMemory(Number(c.memory_mib) / 1024);
                            if (c.disk_gib) setDisk(Number(c.disk_gib));
                            if (typeof c.network_name === "string")
                              setNetwork(c.network_name);
                            setStartAfter(c.start_after_create !== false);
                            setAutostart(c.autostart === true);
                            setHardware((c.hardware as HardwareConfig) || {});
                            setDataDisks((c.data_disks as number[]) || []);
                            setExtraNetworks(
                              (c.additional_networks as string[]) || [],
                            );
                          }
                        }}
                      >
                        <option value="">不使用部署模板</option>
                        {versions.map((v) => (
                          <option key={v.id} value={v.id}>
                            {v.template_name} · v{v.version}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <p className="muted field-wide">
                      部署模板的锁定字段与范围由服务端强制校验；修改后将在提交前检查兼容性。
                    </p>
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
                        disabled={locked.has("image")}
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
                      资源归属于当前账号，并受个人配额及节点授权约束。项目隔离尚未启用。
                    </p>
                  </>
                ) : step === 1 ? (
                  <>
                    <Field
                      label="目标节点"
                      hint="仅列出可调度且持有所选镜像的节点"
                    >
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
                        max={cpuLimit}
                        value={cpu}
                        disabled={locked.has("vcpu")}
                        onChange={(e) => setCpu(Number(e.target.value))}
                      />
                    </Field>
                    <Field label="内存（GB）" hint="0.125–128，步进 0.125">
                      <input
                        type="number"
                        min="0.125"
                        max={memoryLimit}
                        step="0.125"
                        value={memory}
                        disabled={locked.has("memory_mib")}
                        onChange={(e) => setMemory(Number(e.target.value))}
                      />
                    </Field>
                    <HardwareFields
                      value={hardware}
                      onChange={setHardware}
                      caps={caps}
                      cpu={cpu}
                      isAdmin={isAdmin}
                      locked={
                        !isAdmin ||
                        versions
                          .find((v) => v.id === Number(version))
                          ?.constraints.locked?.includes("hardware")
                      }
                    />
                  </>
                ) : step === 2 ? (
                  <>
                    <Field label="系统盘（GB）" hint="1–2048 的整数">
                      <input
                        type="number"
                        min="1"
                        max={diskLimit}
                        value={disk}
                        disabled={locked.has("disk_gib")}
                        onChange={(e) => setDisk(Number(e.target.value))}
                      />
                    </Field>
                    <div className="field-wide">
                      <h4>数据盘（GiB）</h4>
                      {dataDisks.map((size, index) => (
                        <label key={index}>
                          数据盘 {index + 1}
                          <input
                            type="number"
                            min={1}
                            max={2048}
                            disabled={!isAdmin || locked.has("data_disks")}
                            value={size}
                            onChange={(e) =>
                              setDataDisks(
                                dataDisks.map((item, i) =>
                                  i === index ? Number(e.target.value) : item,
                                ),
                              )
                            }
                          />
                          <button
                            className="action"
                            disabled={!isAdmin || locked.has("data_disks")}
                            onClick={() =>
                              setDataDisks(
                                dataDisks.filter((_, i) => i !== index),
                              )
                            }
                          >
                            移除
                          </button>
                        </label>
                      ))}
                      <button
                        className="action"
                        disabled={
                          !isAdmin ||
                          locked.has("data_disks") ||
                          !caps?.multi_disk ||
                          dataDisks.length >= 8
                        }
                        onClick={() => setDataDisks([...dataDisks, 20])}
                      >
                        添加数据盘
                      </button>
                      <p className="muted">
                        所有磁盘合计计入个人配额，当前使用节点配置的磁盘目录。
                      </p>
                    </div>
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
                        disabled={locked.has("network_name")}
                        onChange={(e) => {
                          setNetwork(e.target.value);
                          setExtraNetworks(
                            extraNetworks.filter((n) => n !== e.target.value),
                          );
                        }}
                      >
                        <option value="">不接入网络</option>
                        {networks.map((n) => (
                          <option key={n.id} value={n.name}>
                            {n.name} · {n.type}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="主网卡地址配置">
                      <select
                        value={pool}
                        disabled={!caps?.static_networks}
                        onChange={(e) => {
                          setPool(e.target.value);
                          if (e.target.value) setInitialize(true);
                        }}
                      >
                        <option value="">DHCP</option>
                        {pools.map((p) => (
                          <option key={p.id} value={p.id}>
                            静态地址池：{p.name}
                          </option>
                        ))}
                      </select>
                    </Field>
                    {pool && (
                      <Field
                        label="指定静态 IPv4（可选）"
                        hint="留空由服务端在地址池内分配；需要支持 cloud-init 的镜像和 SSH 公钥"
                      >
                        <input
                          value={staticAddress}
                          onChange={(e) => setStaticAddress(e.target.value)}
                          placeholder="自动分配"
                        />
                      </Field>
                    )}
                    <Field label="网卡型号">
                      <input disabled value={hardware.nic_model || "virtio"} />
                    </Field>
                    <p className="muted field-wide">
                      地址由宿主机实际 DHCP
                      配置分配，静态地址需受控地址池及初始化配置。
                    </p>
                    <Field label="附加网卡（多选，最多 7 个）">
                      <select
                        multiple
                        value={extraNetworks}
                        disabled={
                          !isAdmin ||
                          locked.has("additional_networks") ||
                          !caps?.multi_nic
                        }
                        onChange={(e) =>
                          setExtraNetworks(
                            Array.from(
                              e.target.selectedOptions,
                              (option) => option.value,
                            ),
                          )
                        }
                      >
                        {networks
                          .filter((n) => n.name !== network)
                          .map((n) => (
                            <option key={n.id} value={n.name}>
                              {n.name} · {n.type}
                            </option>
                          ))}
                      </select>
                    </Field>
                  </>
                ) : (
                  <div className="field-wide">
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={initialize}
                        disabled={
                          !caps?.cloud_init ||
                          !selectedImage?.supports_cloud_init ||
                          selectedImage?.format === "ISO"
                        }
                        onChange={(e) => setInitialize(e.target.checked)}
                      />
                      cloud-init 初始化（需镜像确认支持及节点安装 genisoimage）
                    </label>
                    {initialize && (
                      <div className="infra-form">
                        <Field label="主机名（可选）">
                          <input
                            value={hostname}
                            maxLength={63}
                            onChange={(e) => setHostname(e.target.value)}
                          />
                        </Field>
                        <Field label="初始化用户">
                          <input
                            value={guestUser}
                            maxLength={31}
                            onChange={(e) => setGuestUser(e.target.value)}
                          />
                        </Field>
                        <Field label="SSH 公钥（每行一个，不能填私钥）">
                          <textarea
                            rows={4}
                            maxLength={131072}
                            value={sshKeys}
                            onChange={(e) => setSshKeys(e.target.value)}
                          />
                        </Field>
                        <p className="muted">
                          仅交付结构化初始化配置；虚拟机运行不代表初始化已完成。
                        </p>
                      </div>
                    )}
                    <DescList
                      columns={2}
                      items={[
                        ["名称", name],
                        ["镜像", selectedImage?.name],
                        ["节点", selectedNode?.name],
                        ["计算资源", `${cpu} vCPU · ${memory} GB`],
                        ["存储", `${disk} GB · qcow2`],
                        ["网络", network || "不接入"],
                        [
                          "创建行为",
                          startAfter ? "创建后立即启动" : "仅创建，保持关机",
                        ],
                      ]}
                    />
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={startAfter}
                        onChange={(e) => setStartAfter(e.target.checked)}
                      />
                      创建后立即启动
                    </label>
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={autostart}
                        onChange={(e) => setAutostart(e.target.checked)}
                      />
                      宿主机重启后自动启动
                    </label>
                    <p className="muted">
                      提交前会执行服务端预校验；ISO
                      创建表示安装环境就绪，不表示系统已完成安装。
                    </p>
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
                [
                  "数据盘",
                  dataDisks.length
                    ? dataDisks.map((size) => `${size} GiB`).join(" / ")
                    : "无",
                ],
                ["附加网络", extraNetworks.join(" / ") || "无"],
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
                      <span className="muted">
                        剩余 {fmt(Math.max(0, limit - used))}
                      </span>
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
