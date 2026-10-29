import { useEffect, useState } from "react";
import { api } from "../../api";
import { TaskProgressDrawer } from "../../components/ConsoleUI";
import { ErrorBanner, describeError } from "../../components/ui";
import type { Instance, Network } from "../../types";
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
  vcpu: number;
  memory_mib: number;
  disks: Disk[];
  nics: NIC[];
  retained_disks: {
    id: number;
    name: string;
    size_gib: number;
    target_dev: string;
  }[];
};
export function DeviceManager({
  vm,
  admin,
  section,
}: {
  vm: Instance;
  admin: boolean;
  section: "compute" | "disks" | "nics";
}) {
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
  const locked = busy || !stopped || !info || !!task;
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
    if (!admin || section !== "nics") return;
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
  }, [admin, section]);
  async function submit(payload: Record<string, unknown>, description: string) {
    if (locked) return;
    if (
      !window.confirm(
        `${vm.name}：${description}\n变更只应用于已关机实例；下次启动生效。磁盘卸载保留文件，扩容后还需在客体扩展文件系统。确认执行？`,
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.request<{ task: { id: string } }>(
        `/instances/${vm.id}/hardware`,
        { method: "POST", body: JSON.stringify(payload) },
      );
      setTask(result.task.id);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section>
      <h3>
        {
          {
            compute: "CPU 与内存变更",
            disks: "磁盘设备管理",
            nics: "网卡设备管理",
          }[section]
        }
      </h3>
      <ErrorBanner message={error} />
      <button
        className="action sm"
        onClick={() => setRevision((v) => v + 1)}
        disabled={busy}
      >
        刷新节点配置
      </button>
      {!info && !error && <p>正在读取节点实际硬件…</p>}
      {admin && !stopped && (
        <p className="muted">
          请先正常关闭虚拟机，待节点确认后操作。不会自动关机。
        </p>
      )}
      {info && section === "compute" && (
        <>
          <p>
            节点配置：{info.vcpu} vCPU · {info.memory_mib} MiB 内存
          </p>
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
                    <td>{d.target}</td>
                    <td>{d.role}</td>
                    <td>{d.bus}</td>
                    <td>{Math.round(d.size_bytes / 1024 ** 3)} GiB</td>
                    <td>
                      {admin && d.disk_id && d.managed ? (
                        <>
                          <button
                            className="action sm"
                            disabled={locked}
                            onClick={() => {
                              const value = window.prompt(
                                `扩容 ${d.target} 至多少 GiB？仅增加，不格式化。`,
                                String(
                                  Math.round(d.size_bytes / 1024 ** 3) + 10,
                                ),
                              );
                              if (value !== null)
                                void submit(
                                  {
                                    operation: "disk-resize",
                                    disk_id: d.disk_id,
                                    size_gib: Number(value),
                                  },
                                  `扩容 ${d.target} 至 ${value} GiB`,
                                );
                            }}
                          >
                            扩容
                          </button>
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
                          {!admin ? "只读" : "未登记或非受管文件，禁止修改"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {admin && (
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
                  {admin && (
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
                    <td>{n.mac}</td>
                    <td>{n.source}</td>
                    <td>{n.model}</td>
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
          {admin && (
            <div className="infra-form">
              <label>
                业务网络
                <select
                  value={network}
                  disabled={locked}
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
                  disabled={locked}
                  onChange={(e) => setModel(e.target.value)}
                >
                  <option value="virtio">VirtIO（需客体驱动）</option>
                  <option value="e1000e">Intel e1000e</option>
                </select>
              </label>
              <button
                className="action"
                disabled={locked || !network}
                onClick={() =>
                  void submit(
                    { operation: "nic-add", network_name: network, model },
                    `新增 ${model} 网卡连接 ${network}`,
                  )
                }
              >
                添加网卡
              </button>
              <p className="muted field-wide">
                MAC 由后端唯一生成。带静态 IP
                租约记录的网卡暂不自动移除，以免丢失地址分配。新网卡需在客体配置
                DHCP / IP。
              </p>
            </div>
          )}
        </>
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
