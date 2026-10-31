import { useEffect, useState, useRef } from "react";
import { api } from "../../api";
import {
  TaskProgressDrawer,
  ConfirmOperationModal,
} from "../../components/ConsoleUI";
import { ErrorBanner, describeError } from "../../components/ui";
import { Icon } from "../../components/icons";
import type { Instance, Network } from "../../types";
import type { Image } from "../../types";
import { allResources } from "../infrastructure/client";
type Disk = {
  target: string;
  bus: string;
  relative_path: string;
  size_bytes: number;
  managed: boolean;
  disk_id: number | null;
  role: string;
};
type NIC = { mac: string; model: string; source: string; type: string };
type Inventory = {
  cdroms?: {target:string; bus:string; mounted:boolean; source:string}[];
  system?: {
    os: { firmware: string; loader: string; type: { machine: string; arch: string }; boot: { device: string }[] | null };
    cpu: { mode: string; model: string; topology: { sockets: number; cores: number; threads: number } | null };
  };
  vcpu: number;
  memory_mib: number;
  disks: Disk[];
  nics: NIC[];
  retained_disks: {
    id: number;
    name: string;
    size_gib: number;
    target_dev: string;
    role: string;
  }[];
};
export function DeviceManager({
  vm,
  admin,
  manageDataDisks,
  connectNetworks,
  deleteDataDisks,
  section,
}: {
  vm: Instance;
  admin: boolean;
  manageDataDisks: boolean;
  connectNetworks: boolean;
  deleteDataDisks: boolean;
  section: "compute" | "disks" | "nics";
}) {
  const pendingKeys = useRef(new Map<string, string>());
  const [isoImages, setIsoImages] = useState<Image[]>([]);
  const [isoImage, setIsoImage] = useState("");
  useEffect(() => {
    let alive = true;
    if (admin && section === "disks") void allResources<Image>("/images").then((images) => {
      if (alive) setIsoImages(images.filter((image) => image.format === "ISO" && image.status === "READY" && image.node === vm.node));
    }).catch((err) => { if (alive) setError(describeError(err)); });
    return () => { alive = false; };
  }, [admin, section, vm.node]);
  const [confirmation, setConfirmation] = useState<{
      payload: Record<string, unknown>;
      description: string;
      minimum?: number;
    } | null>(null),
    [resizeSize, setResizeSize] = useState(0);
  const [info, setInfo] = useState<Inventory | null>(null),
    [error, setError] = useState<string | null>(null),
    [busy, setBusy] = useState(false),
    [revision, setRevision] = useState(0),
    [task, setTask] = useState<string | null>(null);
  const [cpu, setCpu] = useState(vm.vcpu),
    [memory, setMemory] = useState(vm.memory_mib),
    [size, setSize] = useState(20),
    [bus, setBus] = useState("virtio"),
    [model, setModel] = useState("virtio"),
    [network, setNetwork] = useState(""),
    [networks, setNetworks] = useState<Network[]>([]);
  const stopped =
    vm.observed_state === "SHUTOFF" && !vm.observed_state_is_stale;
  const running =
    vm.observed_state === "RUNNING" && !vm.observed_state_is_stale;
  const canAddDisk = admin || manageDataDisks;
  const canAddNIC = admin || connectNetworks;
  const canEdit =
    admin ||
    (section === "disks" && canAddDisk) ||
    (section === "nics" && canAddNIC);
  const locked = busy || !stopped || !info || !!task;
  const connectLocked = busy || (!stopped && !running) || !info || !!task;
  useEffect(() => {
    let alive = true;
    setInfo(null);
    setError(null);
    api
      .request<Inventory>(`/instances/${vm.id}/hardware`)
      .then((v) => {
        if (alive) {
          setInfo(v);
          setCpu(v.vcpu);
          setMemory(v.memory_mib);
        }
      })
      .catch((e) => {
        if (alive) setError(describeError(e));
      });
    return () => {
      alive = false;
    };
  }, [vm.id, revision]);
  useEffect(() => {
    if (!canAddNIC || section !== "nics") return;
    let alive = true;
    api
      .networks()
      .then((v) => {
        if (alive) setNetworks(v.results.filter((n) => n.is_usable));
      })
      .catch((e) => {
        if (alive) setError(describeError(e));
      });
    return () => {
      alive = false;
    };
  }, [canAddNIC, section]);
  async function submit(
    payload: Record<string, unknown>,
    description: string,
    confirmed = false,
  ) {
    if (payload.operation === "nic-add" ? connectLocked : locked) return;
    if (!confirmed) {
      setError(null);
      setConfirmation({ payload, description });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const storageKey = `cloudvirt-hardware:${vm.id}:${JSON.stringify(payload)}`;
      let key = pendingKeys.current.get(storageKey);
      try {
        key = key || sessionStorage.getItem(storageKey) || undefined;
      } catch {}
      if (!key) {
        key = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) =>
          b.toString(16).padStart(2, "0"),
        ).join("");
      }
      pendingKeys.current.set(storageKey, key);
      try {
        sessionStorage.setItem(storageKey, key);
      } catch {}
      const result = await api.request<{ task: { id: string } }>(
        `/instances/${vm.id}/hardware`,
        {
          method: "POST",
          headers: { "Idempotency-Key": key },
          body: JSON.stringify(payload),
        },
      );
      pendingKeys.current.delete(storageKey);
      try {
        sessionStorage.removeItem(storageKey);
      } catch {}
      setTask(result.task.id);
      setConfirmation(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }
  async function deleteRetainedDisk(id: number) {
    if (busy || !info || !!task || !deleteDataDisks) return;
    setBusy(true);
    setError(null);
    const storageKey = `cloudvirt-disk-delete:${id}`;
    let key = pendingKeys.current.get(storageKey);
    try {
      key = key || sessionStorage.getItem(storageKey) || undefined;
    } catch {}
    if (!key) key = crypto.randomUUID();
    pendingKeys.current.set(storageKey, key);
    try {
      sessionStorage.setItem(storageKey, key);
    } catch {}
    try {
      const result = await api.request<{ task_id: string }>(`/disks/${id}`, {
        method: "DELETE",
        headers: { "Idempotency-Key": key },
      });
      pendingKeys.current.delete(storageKey);
      try {
        sessionStorage.removeItem(storageKey);
      } catch {}
      setTask(result.task_id);
      setConfirmation(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className={`device-manager device-${section}`}>
      <header className="hardware-panel-head">
        <div className="hardware-title">
          <span className="hardware-icon">
            <Icon
              name={{ compute: "cpu", disks: "disk", nics: "network" }[section]}
              size={20}
            />
          </span>
          <div>
            <h3>
              {
                {
                  compute: "CPU 与内存变更",
                  disks: "磁盘设备管理",
                  nics: "网卡设备管理",
                }[section]
              }
            </h3>
            <p>
              {
                {
                  compute: "调整计算规格，变更将在下次启动时生效。",
                  disks: "管理实例存储设备，保留清晰的数据边界。",
                  nics: "连接受控业务网络，查看每一张网卡的配置。",
                }[section]
              }
            </p>
          </div>
        </div>
        <div className="hardware-head-actions">
          <span
            className={`hardware-permission ${canEdit ? "is-admin" : ""}`}
          >
            <Icon name="key" size={13} />
            {admin
              ? "管理员管理"
              : canEdit
                ? "本人资源可操作"
                : "只读访问"}
          </span>
          <button
            className="action sm"
            onClick={() => setRevision((v) => v + 1)}
            disabled={busy}
          >
            <Icon name="refresh" size={14} />
            刷新
          </button>
        </div>
      </header>
      <ErrorBanner message={error} />
      {!info && !error && <p>正在读取节点实际硬件…</p>}
      {canEdit && !stopped && section !== "nics" && (
        <div className="hardware-notice">
          <Icon name="info" size={16} />
          <div>
            <strong>
              {vm.observed_state === "RUNNING"
                ? "运行中 · 硬件变更暂不可用"
                : "状态待确认 · 硬件变更暂不可用"}
            </strong>
            <span>请先正常关闭虚拟机，等待节点确认。平台不会自动关机。</span>
          </div>
        </div>
      )}
      {info && section !== "compute" && (
        <div className="hardware-kpis">
          <div>
            <span>{section === "disks" ? "已挂载磁盘" : "已连接网卡"}</span>
            <strong>
              {section === "disks" ? info.disks.length : info.nics.length}
              <small> 个</small>
            </strong>
          </div>
          <div>
            <span>{section === "disks" ? "虚拟容量合计" : "关联网络"}</span>
            <strong>
              {section === "disks"
                ? Math.round(
                    info.disks.reduce((n, d) => n + d.size_bytes, 0) /
                      1024 ** 3,
                  )
                : new Set(info.nics.map((n) => n.source)).size}
              <small>{section === "disks" ? " GiB" : " 个"}</small>
            </strong>
          </div>
          <div>
            <span>{section === "disks" ? "保留磁盘" : "变更方式"}</span>
            <strong>
              {section === "disks"
                ? info.retained_disks.length
                : "运行中可热接入"}
              <small>{section === "disks" ? " 个" : ""}</small>
            </strong>
          </div>
        </div>
      )}
      {info && section === "compute" && (
        <>
          <div className="table-scroll">
            <table aria-label="节点实际硬件配置">
              <thead><tr><th>硬件</th><th>节点实际配置</th><th>操作范围</th></tr></thead>
              <tbody>
                <tr><td>处理器</td><td>{info.vcpu} vCPU · {info.system?.cpu.mode || info.system?.cpu.model || "节点默认"}</td><td>{admin ? "关机后可修改核数" : "只读"}</td></tr>
                <tr><td>内存</td><td>{info.memory_mib / 1024} GiB</td><td>{admin ? "关机后可修改" : "只读"}</td></tr>
                <tr><td>CPU 拓扑</td><td>{info.system?.cpu.topology ? `${info.system.cpu.topology.sockets} 插槽 × ${info.system.cpu.topology.cores} 核 × ${info.system.cpu.topology.threads} 线程` : "未显式配置"}</td><td>创建时配置</td></tr>
                <tr><td>固件</td><td>{info.system ? info.system.os.firmware || (info.system.os.loader ? "UEFI / pflash" : "BIOS") : "节点未返回"}</td><td>创建时配置</td></tr>
                <tr><td>机型 / 架构</td><td>{info.system ? `${info.system.os.type.machine || "节点默认"} · ${info.system.os.type.arch || "未返回"}` : "节点未返回"}</td><td>节点实际机型</td></tr>
                <tr><td>启动设备顺序</td><td>{info.system?.os.boot?.map((item) => item.device).join(" → ") || "节点默认或设备级启动顺序"}</td><td>按节点域定义显示</td></tr>
                <tr><td>磁盘 / 网卡</td><td>{info.disks.length} 块磁盘 · {info.nics.length} 张网卡</td><td>在磁盘、网络标签管理</td></tr>
              </tbody>
            </table>
          </div>
          <div className="hardware-kpis">
            <div>
              <span>当前处理器</span>
              <strong>
                {info.vcpu}
                <small> vCPU</small>
              </strong>
            </div>
            <div>
              <span>当前内存</span>
              <strong>
                {info.memory_mib / 1024}
                <small> GiB</small>
              </strong>
            </div>
            <div>
              <span>生效方式</span>
              <strong>下次启动</strong>
            </div>
          </div>
          {admin && (
            <div className="infra-form">
              <label>
                vCPU
                <input
                  type="number"
                  min={1}
                  max={128}
                  value={cpu}
                  disabled={locked}
                  onChange={(e) => setCpu(Number(e.target.value))}
                />
              </label>
              <label>
                内存 MiB
                <input
                  type="number"
                  min={128}
                  max={1048576}
                  value={memory}
                  disabled={locked}
                  onChange={(e) => setMemory(Number(e.target.value))}
                />
              </label>
              <p className="muted field-wide">
                CPU 拓扑设为 1 插槽 × N 核 × 1 线程。存在 NUMA、直通或 CPU
                绑定时拒绝自动修改。
              </p>
              <button
                className="action"
                disabled={locked}
                onClick={() =>
                  void submit(
                    { operation: "compute", vcpu: cpu, memory_mib: memory },
                    `调整为 ${cpu} vCPU、${memory} MiB 内存`,
                  )
                }
              >
                保存 CPU / 内存
              </button>
            </div>
          )}
        </>
      )}
      {info && section === "disks" && (
        <>
          <section className="card">
            <h3>安装光驱 · ISO 镜像</h3>
            <p className="muted">安装光驱使用 SATA sda，修改前须关机。弹出或移除光驱不删除镜像文件；cloud-init 光驱不在此处修改。</p>
            {(info.cdroms || []).map((drive) => <p key={drive.target}>{drive.target} · {drive.bus} · {drive.mounted ? drive.source.split("/").pop() : "无介质"}</p>)}
            {admin && <div className="infra-form">
              <label>安装 ISO<select value={isoImage} disabled={locked} onChange={(e) => setIsoImage(e.target.value)}>
                <option value="">选择本节点已就绪的 ISO</option>
                {isoImages.map((image) => <option key={image.id} value={image.id}>{image.name} · {image.storage_pool_name || "节点原有镜像目录"}</option>)}
              </select></label>
              <div className="device-actions">
                <button className="action" disabled={locked || !isoImage || !info.cdroms || info.disks.some((disk) => disk.target === "sda")} onClick={() => void submit({operation:"cdrom-set",target:"sda",image_id:Number(isoImage)},"挂载或更换安装 ISO，设置光驱优先启动")}>挂载 / 更换 ISO</button>
                <button className="action danger" disabled={locked || !info.cdroms?.some((drive) => drive.target === "sda")} onClick={() => void submit({operation:"cdrom-remove",target:"sda"},"弹出安装介质并移除安装光驱（保留 ISO 文件）")}>弹出 / 移除光驱</button>
              </div>
              {!info.cdroms && <p className="muted">节点尚未返回光驱清单，请升级 Agent。</p>}
              {info.disks.some((disk) => disk.target === "sda") && <p className="muted">sda 已被磁盘占用，禁止替换为光驱。</p>}
            </div>}
          </section>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>设备</th>
                  <th>角色</th>
                  <th>总线</th>
                  <th>容量</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {info.disks.map((d) => (
                  <tr key={d.target}>
                    <td>
                      <div className="hardware-device-cell">
                        <span className="device-glyph">
                          <Icon name="volume" size={18} />
                        </span>
                        <div>
                          <strong>{d.target}</strong>
                          <small>{d.managed ? "受管 QCOW2" : "外部设备"}</small>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span
                        className={`hardware-tag ${d.role === "SYSTEM" ? "tag-system" : ""}`}
                      >
                        {d.role === "SYSTEM"
                          ? "系统盘"
                          : d.role === "DATA"
                            ? "数据盘"
                            : d.role}
                      </span>
                    </td>
                    <td>
                      <code className="hardware-bus">
                        {d.bus.toUpperCase()}
                      </code>
                    </td>
                    <td>{Math.round(d.size_bytes / 1024 ** 3)} GiB</td>
                    <td>
                      {(admin || (manageDataDisks && d.role === "DATA")) &&
                      d.disk_id &&
                      d.managed ? (
                        <>
                          {admin && (
                            <button
                              className="action sm"
                              disabled={locked}
                              onClick={() => {
                                const current = Math.round(
                                  d.size_bytes / 1024 ** 3,
                                );
                                setResizeSize(Math.min(2048, current + 10));
                                setError(null);
                                setConfirmation({
                                  payload: {
                                    operation: "disk-resize",
                                    disk_id: d.disk_id,
                                  },
                                  description: `扩容磁盘 ${d.target}，当前容量 ${current} GiB`,
                                  minimum: current,
                                });
                              }}
                            >
                              扩容
                            </button>
                          )}
                          {d.role === "DATA" && (
                            <button
                              className="action sm danger"
                              disabled={locked}
                              onClick={() =>
                                void submit(
                                  {
                                    operation: "disk-detach",
                                    disk_id: d.disk_id,
                                  },
                                  `卸载数据盘 ${d.target}，保留磁盘文件`,
                                )
                              }
                            >
                              卸载 / 保留文件
                            </button>
                          )}
                        </>
                      ) : (
                        <span className="muted">
                          {!admin && !manageDataDisks
                            ? "只读"
                            : "系统盘或未登记文件，禁止修改"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {canAddDisk && (
            <div className="infra-form">
              <label>
                数据盘容量 GiB
                <input
                  type="number"
                  min={1}
                  max={2048}
                  value={size}
                  disabled={locked}
                  onChange={(e) => setSize(Number(e.target.value))}
                />
              </label>
              <label>
                总线
                <select
                  value={bus}
                  disabled={locked}
                  onChange={(e) => setBus(e.target.value)}
                >
                  <option value="virtio">VirtIO（需客体驱动）</option>
                  <option value="sata">SATA</option>
                </select>
              </label>
              <button
                className="action"
                disabled={locked}
                onClick={() =>
                  void submit(
                    { operation: "disk-add", size_gib: size, bus },
                    `新增 ${size} GiB ${bus} 数据盘`,
                  )
                }
              >
                添加数据盘
              </button>
            </div>
          )}
          {!!info.retained_disks.length && (
            <>
              <h4>已卸载并保留的磁盘（继续占用容量与配额）</h4>
              {info.retained_disks.map((d) => (
                <p key={d.id}>
                  {d.name} · {d.size_gib} GiB{" "}
                  {(admin || (manageDataDisks && d.role === "DATA")) && (
                    <button
                      className="action sm"
                      disabled={locked}
                      onClick={() =>
                        void submit(
                          { operation: "disk-attach", disk_id: d.id },
                          `重新挂载 ${d.name}`,
                        )
                      }
                    >
                      重新挂载
                    </button>
                  )}
                  {deleteDataDisks && d.role === "DATA" && (
                    <button
                      className="action sm danger"
                      disabled={busy || !info || !!task}
                      onClick={() =>
                        setConfirmation({
                          payload: { operation: "disk-delete", disk_id: d.id },
                          description: `永久删除已卸载数据盘 ${d.name}（${d.size_gib} GiB）及其文件`,
                        })
                      }
                    >
                      删除文件
                    </button>
                  )}
                </p>
              ))}
            </>
          )}
        </>
      )}
      {info && section === "nics" && (
        <>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>MAC</th>
                  <th>连接</th>
                  <th>型号</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {info.nics.map((n) => (
                  <tr key={n.mac}>
                    <td>
                      <div className="hardware-device-cell">
                        <span className="device-glyph">
                          <Icon name="network" size={18} />
                        </span>
                        <strong className="mono">{n.mac}</strong>
                      </div>
                    </td>
                    <td>
                      <span className="hardware-network-dot" />
                      {n.source}
                    </td>
                    <td>
                      <code className="hardware-bus">{n.model}</code>
                    </td>
                    <td>
                      {admin ? (
                        <button
                          className="action danger sm"
                          disabled={locked}
                          onClick={() =>
                            void submit(
                              { operation: "nic-remove", mac: n.mac },
                              `移除网卡 ${n.mac}（${n.source}），客体网络配置可能需要调整`,
                            )
                          }
                        >
                          移除网卡
                        </button>
                      ) : (
                        "只读"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {canAddNIC && (
            <div className="infra-form">
              <label>
                业务网络
                <select
                  value={network}
                  disabled={connectLocked}
                  onChange={(e) => setNetwork(e.target.value)}
                >
                  <option value="">选择白名单网络</option>
                  {networks.map((n) => (
                    <option key={n.id} value={n.name}>
                      {n.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                网卡型号
                <select
                  value={model}
                  disabled={connectLocked}
                  onChange={(e) => setModel(e.target.value)}
                >
                  <option value="virtio">VirtIO（需客体驱动）</option>
                  <option value="e1000e">Intel e1000e</option>
                </select>
              </label>
              <button
                className="action"
                disabled={connectLocked || !network}
                onClick={() =>
                  void submit(
                    {
                      operation: "nic-add",
                      network_name: network,
                      model,
                      ...(running ? { live: true } : {}),
                    },
                    `新增 ${model} 网卡连接 ${network}`,
                  )
                }
              >
                添加网卡
              </button>
              <p className="muted field-wide">
                运行中将热接入网卡；MAC 由后端唯一生成。带静态 IP
                租约记录的网卡暂不自动移除，以免丢失地址分配。新网卡需在客体配置
                DHCP / IP。
              </p>
            </div>
          )}
        </>
      )}
      {confirmation && (
        <ConfirmOperationModal
          target={vm.name}
          operation={
            (
              {
                compute: "调整计算规格",
                "disk-add": "添加数据盘",
                "disk-detach": "卸载数据盘",
                "disk-attach": "重新挂载",
                "disk-resize": "扩容磁盘",
                "disk-delete": "永久删除数据盘文件",
                "nic-add": "添加网卡",
                "nic-remove": "移除网卡",
              } as Record<string, string>
            )[String(confirmation.payload.operation)]
          }
          description={confirmation.description}
          busy={busy}
          error={error}
          onCancel={() => {
            setConfirmation(null);
            setError(null);
          }}
          onConfirm={() => {
            if (
              confirmation.minimum !== undefined &&
              (!Number.isInteger(resizeSize) ||
                resizeSize <= confirmation.minimum ||
                resizeSize > 2048)
            ) {
              setError("目标容量必须大于当前容量，且不超过 2048 GiB");
              return;
            }
            if (confirmation.payload.operation === "disk-delete") {
              void deleteRetainedDisk(Number(confirmation.payload.disk_id));
            } else {
              void submit(
                confirmation.minimum === undefined
                  ? confirmation.payload
                  : { ...confirmation.payload, size_gib: resizeSize },
                confirmation.description,
                true,
              );
            }
          }}
        >
          <div
            className="hardware-confirm-body"
            data-danger={["disk-detach", "disk-delete", "nic-remove"].includes(
              String(confirmation.payload.operation),
            )}
          >
            {confirmation.minimum !== undefined && (
              <label>
                目标容量（GiB）
                <input
                  type="number"
                  min={confirmation.minimum + 1}
                  max={2048}
                  value={resizeSize}
                  onChange={(e) => setResizeSize(Number(e.target.value))}
                />
              </label>
            )}
            <p>
              磁盘变更需先关机；卸载后文件仍保留，删除文件不可恢复。运行中新增网卡需客体驱动支持。
            </p>
          </div>
        </ConfirmOperationModal>
      )}
      {task && (
        <TaskProgressDrawer
          id={task}
          onClose={() => {
            setTask(null);
            setRevision((v) => v + 1);
          }}
        />
      )}
    </section>
  );
}
