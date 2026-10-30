import { useEffect, useState } from "react";
import { api } from "../../api";
import { Card, ErrorBanner, describeError } from "../../components/ui";
import type { Image, Node, Network, User } from "../../types";
import {
  HardwareFields,
  type HardwareConfig,
  type CreationCapabilities,
} from "./HardwareFields";

export type DeploymentVersion = {
  id: number;
  template: number;
  template_name: string;
  version: number;
  configuration: Record<string, unknown>;
  constraints: Record<string, unknown>;
  created_at: string;
  name?: string;
  description?: string;
  is_public?: boolean;
  assigned_users?: number[];
};

export function DeploymentTemplateEditor({
  editing,
  onSaved,
}: {
  editing?: DeploymentVersion | null;
  onSaved: () => void;
}) {
  const [images, setImages] = useState<Image[]>([]),
    [name, setName] = useState(editing?.template_name || ""),
    [description, setDescription] = useState(editing?.description || ""),
    [isPublic, setIsPublic] = useState(editing?.is_public ?? true),
    [assigned, setAssigned] = useState<number[]>(editing?.assigned_users || []),
    [users, setUsers] = useState<User[]>([]),
    [userSearch, setUserSearch] = useState(""),
    [image, setImage] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  const [start, setStart] = useState(true),
    [autostart, setAutostart] = useState(false);
  const [vcpu, setVcpu] = useState(2),
    [memoryGiB, setMemoryGiB] = useState(2),
    [systemDisk, setSystemDisk] = useState(20);
  const [initialize, setInitialize] = useState(false),
    [guestUser, setGuestUser] = useState("cloudvirt"),
    [sshKeys, setSshKeys] = useState("");
  const [hardware, setHardware] = useState<HardwareConfig>({}),
    [dataDisks, setDataDisks] = useState<number[]>([]),
    [extraNetworks, setExtraNetworks] = useState<string[]>([]),
    [network, setNetwork] = useState(""),
    [networks, setNetworks] = useState<Network[]>([]),
    [nodes, setNodes] = useState<Node[]>([]),
    [node, setNode] = useState(""),
    [caps, setCaps] = useState<CreationCapabilities | null>(null);
  useEffect(() => {
    if (!editing) return;
    const c = editing.configuration;
    setImage(String(c.image || ""));
    setNode(String(c.node || ""));
    setVcpu(Number(c.vcpu || 2));
    setMemoryGiB(Number(c.memory_mib || 2048) / 1024);
    setSystemDisk(Number(c.disk_gib || 20));
    setStart(c.start_after_create !== false);
    setAutostart(c.autostart === true);
    setHardware((c.hardware as HardwareConfig) || {});
    setDataDisks((c.data_disks as number[]) || []);
    setExtraNetworks((c.additional_networks as string[]) || []);
    setNetwork(String(c.network_name || ""));
    const init = c.initialization as
      | { username?: string; ssh_public_keys?: string[] }
      | undefined;
    setInitialize(Boolean(init));
    if (init) {
      setGuestUser(init.username || "cloudvirt");
      setSshKeys((init.ssh_public_keys || []).join("\n"));
    }
  }, [editing]);
  useEffect(() => {
    let alive = true;
    const timer = setTimeout(() => {
      api
        .request<{ results: User[] }>(
          `/users?page_size=100&search=${encodeURIComponent(userSearch)}`,
        )
        .then((v) => {
          if (alive) setUsers(v.results);
        })
        .catch((e) => {
          if (alive) setError(describeError(e));
        });
    }, 250);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [userSearch]);
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
    try {
      if (!name.trim() || !image || !node)
        throw Error("请填写模板名称、选择可用镜像和目标节点");
      const configuration = {
        node: Number(node),
        ...(initialize
          ? {
              initialization: {
                username: guestUser,
                ssh_public_keys: sshKeys
                  .split(/\r?\n/)
                  .map((s) => s.trim())
                  .filter(Boolean),
              },
            }
          : {}),
        hardware,
        data_disks: dataDisks,
        additional_networks: extraNetworks,
        network_name: network,
        image: Number(image),
        vcpu,
        memory_mib: Math.round(memoryGiB * 1024),
        disk_gib: systemDisk,
        start_after_create: start,
        autostart,
      };
      await api.request(
        editing ? `/template-versions/${editing.id}` : "/templates/deployments",
        {
          method: editing ? "PATCH" : "POST",
          body: JSON.stringify({
            name: name.trim(),
            description,
            is_public: isPublic,
            assigned_users: assigned,
            configuration,
            constraints: {
              locked: [
                "hardware",
                "data_disks",
                "image",
                "node",
                "vcpu",
                "memory_mib",
                "disk_gib",
                "autostart",
                "start_after_create",
              ],
            },
          }),
        },
      );
      onSaved();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card
      title={
        editing
          ? `编辑部署模板：${editing.template_name} v${editing.version}`
          : "新建部署模板"
      }
      description="将规格、镜像与设备配置固化为可交付的版本。"
      className="deployment-editor"
    >
      <div className="deployment-flow">
        <span>
          <b>01</b>基本信息与镜像
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
        配置完整部署参数与使用范围，发布后进入模板库；编辑将发布替代版本，不修改已有虚拟机。
      </p>
      <ErrorBanner message={error} />
      <form className="inline deployment-form" onSubmit={publish}>
        <label>
          模板名称
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            minLength={2}
            maxLength={64}
          />
        </label>
        <label>
          说明
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={200}
          />
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={isPublic}
            onChange={(e) => setIsPublic(e.target.checked)}
          />
          公开可用
        </label>
        <fieldset style={{ gridColumn: "1 / -1", minWidth: 0 }}>
          <legend>定向授权用户</legend>
          <input
            aria-label="搜索授权用户"
            placeholder="搜索用户"
            value={userSearch}
            onChange={(e) => setUserSearch(e.target.value)}
          />
          <div className="table-scroll" style={{ maxHeight: 160 }}>
            {users.map((u) => (
              <label className="check" key={u.id}>
                <input
                  type="checkbox"
                  checked={assigned.includes(u.id)}
                  onChange={(e) =>
                    setAssigned((previous) =>
                      e.target.checked
                        ? [...previous, u.id]
                        : previous.filter((id) => id !== u.id),
                    )
                  }
                />
                {u.username}
              </label>
            ))}
          </div>
          <small className="muted">
            关闭公开后仅授权用户可用，已选 {assigned.length}{" "}
            人；不授予硬件修改权限。
          </small>
        </fieldset>
        <label>
          系统镜像
          <select
            value={image}
            onChange={(e) => {
              setImage(e.target.value);
              setNode("");
              setInitialize(false);
            }}
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
          部署目标节点
          <select
            required
            value={node}
            onChange={(e) => setNode(e.target.value)}
          >
            <option value="">选择持有镜像的节点</option>
            {nodes
              .filter(
                (n) =>
                  n.is_schedulable &&
                  (!images.find((i) => i.id === Number(image))?.node ||
                    images.find((i) => i.id === Number(image))?.node === n.id),
              )
              .map((n) => (
                <option key={n.id} value={n.id}>
                  {n.name}
                </option>
              ))}
          </select>
        </label>
        <label>
          vCPU（核）
          <input
            required
            type="number"
            min={1}
            max={64}
            value={vcpu}
            onChange={(e) => setVcpu(Number(e.target.value))}
          />
        </label>
        <label>
          内存（GiB）
          <input
            required
            type="number"
            min={0.125}
            max={128}
            step={0.125}
            value={memoryGiB}
            onChange={(e) => setMemoryGiB(Number(e.target.value))}
          />
        </label>
        <label>
          系统盘（GiB）
          <input
            required
            type="number"
            min={1}
            max={2048}
            value={systemDisk}
            onChange={(e) => setSystemDisk(Number(e.target.value))}
          />
        </label>
        <HardwareFields
          value={hardware}
          onChange={setHardware}
          caps={caps}
          cpu={vcpu}
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
        <p className="muted field-wide">
          发布后
          CPU、内存、磁盘、硬件和启动策略固定继承。使用者仅填写名称并为模板网卡选择网络。
        </p>
        <label className="check field-wide">
          <input
            type="checkbox"
            checked={initialize}
            disabled={
              !caps?.cloud_init ||
              !images.find((i) => i.id === Number(image))?.supports_cloud_init
            }
            onChange={(e) => setInitialize(e.target.checked)}
          />
          cloud-init 初始化（仅已审核支持的磁盘镜像）
        </label>
        {initialize && (
          <>
            <label>
              客体用户名
              <input
                required
                value={guestUser}
                onChange={(e) => setGuestUser(e.target.value)}
                placeholder="cloudvirt"
              />
            </label>
            <label className="field-wide">
              SSH 公钥
              <textarea
                required
                value={sshKeys}
                onChange={(e) => setSshKeys(e.target.value)}
                rows={3}
                placeholder="每行一个 SSH 公钥；会应用到该模板的每台实例"
              />
            </label>
          </>
        )}
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
          {busy
            ? "正在校验并发布…"
            : editing
              ? "保存并发布替代版本"
              : "创建并发布模板"}
        </button>
      </form>
    </Card>
  );
}
