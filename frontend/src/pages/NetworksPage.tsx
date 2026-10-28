import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { NetworkTopology } from "../components/NetworkTopology";
import { Drawer, ConfirmOperationModal, PageHeader } from "../components/ConsoleUI";
import { validateAddress } from "../features/networks/validateAddress";
import {
  Card,
  Empty,
  ErrorBanner,
  StatusBadge,
  describeError,
} from "../components/ui";
import { can } from "../permissions";
import type {
  CurrentUser,
  Instance,
  InstanceInterface,
  Network,
} from "../types";

const NETWORK_TYPES = [
  { value: "LIBVIRT_NETWORK", label: "libvirt 网络" },
  { value: "BRIDGE", label: "Linux 网桥" },
  { value: "OVS", label: "Open vSwitch 网桥" },
];

const TYPE_LABEL = new Map(
  NETWORK_TYPES.map((item) => [item.value, item.label]),
);

type NetworkForm = {
  name: string;
  type: string;
  bridge: string;
  vlan: string;
  is_default: boolean;
  is_management: boolean;
  subnet: string;
  gateway: string;
  dhcp_enabled: boolean;
  dhcp_start: string;
  dhcp_end: string;
  dns_servers: string;
  description: string;
};

const EMPTY_FORM: NetworkForm = {
  name: "",
  type: "LIBVIRT_NETWORK",
  bridge: "",
  vlan: "",
  is_default: false,
  is_management: false,
  subnet: "",
  gateway: "",
  dhcp_enabled: false,
  dhcp_start: "",
  dhcp_end: "",
  dns_servers: "",
  description: "",
};

export function NetworksPage({ user }: { user: CurrentUser }) {
  const [networks, setNetworks] = useState<Network[]>([]);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [interfaces, setInterfaces] = useState<
    Record<number, InstanceInterface[]>
  >({});
  const [view, setView] = useState<"list" | "topology">("list");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<NetworkForm>(EMPTY_FORM);
  const [editing, setEditing] = useState<Network | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [networkStep, setNetworkStep] = useState(0);
  const [deleting, setDeleting] = useState<Network | null>(null);
  const [selectedNetwork, setSelectedNetwork] = useState<Network | null>(null);

  const canManage = can(user, "networks.manage_network");

  const reload = useCallback(async () => {
    try {
      const [networkPage, instancePage] = await Promise.all([
        api.networks(),
        api.instances(),
      ]);
      setNetworks(networkPage.results);
      setInstances(instancePage.results);
      const running = instancePage.results.filter(
        (instance) => instance.observed_state === "RUNNING",
      );
      if (running.length === 0) {
        setInterfaces({});
      } else {
        void Promise.all(
          running.map(async (instance) => {
            try {
              const data = await api.instanceInterfaces(instance.id);
              return [instance.id, data.interfaces] as const;
            } catch {
              return [instance.id, []] as const;
            }
          }),
        ).then((entries) => setInterfaces(Object.fromEntries(entries)));
      }
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  function resetForm() {
    setNetworkStep(0);
    setForm(EMPTY_FORM);
    setEditing(null);
  }

  function startEdit(network: Network) {
    setNetworkStep(0);
    setShowForm(true);
    setEditing(network);
    setForm({
      name: network.name,
      type: network.type,
      bridge: network.bridge,
      vlan: network.vlan_id == null ? "" : String(network.vlan_id),
      is_default: network.is_default,
      is_management: network.is_management,
      subnet: network.subnet || "",
      gateway: network.gateway || "",
      dhcp_enabled: network.dhcp_enabled,
      dhcp_start: network.dhcp_start || "",
      dhcp_end: network.dhcp_end || "",
      dns_servers: network.dns_servers || "",
      description: network.description,
    });
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    const payload = {
      name: form.name,
      type: form.type,
      bridge: form.bridge,
      vlan_id: form.vlan ? Number(form.vlan) : null,
      is_default: form.is_default,
      is_management: form.is_management,
      subnet: form.subnet,
      gateway: form.gateway || null,
      dhcp_enabled: form.dhcp_enabled,
      dhcp_start: form.dhcp_start || null,
      dhcp_end: form.dhcp_end || null,
      dns_servers: form.dns_servers,
      description: form.description,
    };
    try {
      if (editing) {
        await api.updateNetwork(editing.id, payload);
        setNotice(`网络 ${form.name} 已更新`);
      } else {
        await api.createNetwork(payload);
        setNotice(`网络 ${form.name} 已登记`);
      }
      resetForm();
      setShowForm(false);
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(network: Network) {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.deleteNetwork(network.id);
      setNotice(`网络 ${network.name} 已删除`);
      setDeleting(null);
      if (editing?.id === network.id) resetForm();
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="网络白名单"
        description="登记宿主机网桥 / VLAN 与地址规划，仅白名单内网络可供虚拟机接入"
      >
          {canManage ? (
            <button
              className="action primary"
              onClick={() => {
                resetForm();
                setShowForm(true);
              }}
            >
              登记网络
            </button>
          ) : null}
          <button
            className={`action${view === "list" ? " primary" : ""}`}
            onClick={() => setView("list")}
          >
            列表
          </button>
          <button
            className={`action${view === "topology" ? " primary" : ""}`}
            onClick={() => setView("topology")}
          >
            拓扑
          </button>
          <button className="action" onClick={() => void reload()}>
            刷新
          </button>
      </PageHeader>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      {canManage && showForm ? (
        <Drawer
          title={editing ? `编辑网络 · ${editing.name}` : "登记网络"}
          onClose={() => setShowForm(false)}
          wide
          footer={
            <>
              <span className="drawer-foot-hint">
                第 {networkStep + 1} / 5 步
              </span>
              <button
                className="action"
                type="button"
                disabled={busy}
                onClick={() => setShowForm(false)}
              >
                取消
              </button>
              <button
                className="action"
                type="button"
                disabled={networkStep === 0 || busy}
                onClick={() => setNetworkStep(networkStep - 1)}
              >
                上一步
              </button>
              <button
                className="action primary"
                type="submit"
                form="network-wizard-form"
                disabled={busy}
              >
                {busy
                  ? "提交中…"
                  : networkStep === 4
                    ? "确认保存记录"
                    : "下一步"}
              </button>
            </>
          }
        >
            <ol className="wizard-steps wizard-steps-compact">
              {["基本信息", "网络模式", "地址配置", "节点范围", "确认"].map(
                (label, index) => (
                  <li
                    key={label}
                    className={
                      networkStep === index
                        ? "active"
                        : index < networkStep
                          ? "complete"
                          : ""
                    }
                    aria-current={networkStep === index ? "step" : undefined}
                  >
                    <span>{index + 1}</span>
                    <em>{label}</em>
                  </li>
                ),
              )}
            </ol>
            <ErrorBanner message={error} />
            <form
              id="network-wizard-form"
              className="wizard-fields drawer-fields"
              onSubmit={(event) => {
                event.preventDefault();
                if (networkStep === 2) {
                  const validation = validateAddress(
                    form,
                    networks
                      .filter((n) => n.id !== editing?.id)
                      .map((n) => n.subnet),
                  );
                  if (validation) {
                    setError(validation);
                    return;
                  }
                }
                setError(null);
                if (networkStep < 4) {
                  setNetworkStep(networkStep + 1);
                  return;
                }
                void submit(event);
              }}
            >
              {networkStep === 0 ? (
                <>
                  <label>
                    网络名称
                    <input
                      required
                      value={form.name}
                      pattern="[A-Za-z0-9_-]{2,64}"
                      onChange={(e) =>
                        setForm({ ...form, name: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    说明
                    <input
                      value={form.description}
                      onChange={(e) =>
                        setForm({ ...form, description: e.target.value })
                      }
                    />
                  </label>
                </>
              ) : null}
              {networkStep === 1 ? (
                <>
                  <label>
                    连接类型
                    <select
                      value={form.type}
                      onChange={(e) =>
                        setForm({ ...form, type: e.target.value })
                      }
                    >
                      {NETWORK_TYPES.map((type) => (
                        <option key={type.value} value={type.value}>
                          {type.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    网桥名称
                    <input
                      required={form.type !== "LIBVIRT_NETWORK"}
                      value={form.bridge}
                      onChange={(e) =>
                        setForm({ ...form, bridge: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    VLAN ID
                    <input
                      type="number"
                      min={1}
                      max={4094}
                      value={form.vlan}
                      onChange={(e) =>
                        setForm({ ...form, vlan: e.target.value })
                      }
                    />
                  </label>
                </>
              ) : null}
              {networkStep === 2 ? (
                <>
                  <label>
                    子网 CIDR
                    <input
                      value={form.subnet}
                      onChange={(e) =>
                        setForm({ ...form, subnet: e.target.value })
                      }
                      placeholder="192.168.150.0/24"
                    />
                  </label>
                  <label>
                    网关
                    <input
                      value={form.gateway}
                      onChange={(e) =>
                        setForm({ ...form, gateway: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    DNS 服务器
                    <input
                      value={form.dns_servers}
                      onChange={(e) =>
                        setForm({ ...form, dns_servers: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    DHCP
                    <select
                      value={String(form.dhcp_enabled)}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          dhcp_enabled: e.target.value === "true",
                        })
                      }
                    >
                      <option value="false">关闭</option>
                      <option value="true">开启</option>
                    </select>
                  </label>
                  {form.dhcp_enabled ? (
                    <>
                      <label>
                        地址池起始
                        <input
                          required
                          value={form.dhcp_start}
                          onChange={(e) =>
                            setForm({ ...form, dhcp_start: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        地址池结束
                        <input
                          required
                          value={form.dhcp_end}
                          onChange={(e) =>
                            setForm({ ...form, dhcp_end: e.target.value })
                          }
                        />
                      </label>
                    </>
                  ) : null}
                </>
              ) : null}
              {networkStep === 3 ? (
                <>
                  <label className="field-wide">
                    节点范围
                    <input
                      disabled
                      value="平台白名单；每个目标宿主机均需预先配置"
                    />
                  </label>
                  <label>
                    默认网络
                    <select
                      value={String(form.is_default)}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          is_default: e.target.value === "true",
                          is_management:
                            e.target.value === "true"
                              ? false
                              : form.is_management,
                        })
                      }
                    >
                      <option value="false">否</option>
                      <option value="true">是</option>
                    </select>
                  </label>
                  <label>
                    管理网络
                    <select
                      value={String(form.is_management)}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          is_management: e.target.value === "true",
                          is_default:
                            e.target.value === "true" ? false : form.is_default,
                        })
                      }
                    >
                      <option value="false">否</option>
                      <option value="true">是（禁止虚拟机接入）</option>
                    </select>
                  </label>
                  <p className="muted field-wide">
                    当前 API 尚未提供按节点绑定网络的能力。
                  </p>
                </>
              ) : null}
              {networkStep === 4 ? (
                <dl className="info-grid field-wide">
                  <dt>名称</dt>
                  <dd>{form.name}</dd>
                  <dt>类型</dt>
                  <dd>{form.type}</dd>
                  <dt>网桥 / VLAN</dt>
                  <dd>
                    {form.bridge || "—"} / {form.vlan || "—"}
                  </dd>
                  <dt>子网 / 网关</dt>
                  <dd>
                    {form.subnet || "—"} / {form.gateway || "—"}
                  </dd>
                  <dt>DHCP</dt>
                  <dd>
                    {form.dhcp_enabled
                      ? form.dhcp_start + " – " + form.dhcp_end
                      : "关闭"}
                  </dd>
                </dl>
              ) : null}
            </form>
            <div className="callout callout-muted">
              管理网禁止接入虚拟机；默认网络与管理网不能同时勾选。OVS
              网络需先在宿主机创建对应 OVS 网桥， 创建虚拟机时会注入 openvswitch
              虚拟端口并按 VLAN 打标签。子网与 DHCP 配置会持久化并在拓扑中展示；
              DHCP/NAT
              由宿主机独立服务提供。此表单保存白名单与配置说明，修改后须在宿主机应用并核验，当前不代表配置已经生效。
            </div>
        </Drawer>
      ) : null}
      {view === "topology" ? (
        <Card title="网络与接口拓扑">
          <NetworkTopology
            networks={networks}
            instances={instances}
            interfaces={interfaces}
          />
        </Card>
      ) : null}
      {view === "list" ? (
        <Card title={`共 ${networks.length} 个网络`}>
          {networks.length === 0 ? (
            <Empty
              text={
                canManage
                  ? "尚未登记网络，请先在上方登记节点上已验证的网络。"
                  : "尚未登记网络。"
              }
            />
          ) : (
            <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>类型</th>
                  <th>桥接</th>
                  <th>VLAN</th>
                  <th>子网 / 网关</th>
                  <th>DHCP</th>
                  <th>属性</th>
                  <th>说明</th>
                  <th className="col-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                {networks.map((network) => (
                  <tr key={network.id}>
                    <td>
                      <button
                        className="text-link"
                        onClick={() => setSelectedNetwork(network)}
                      >
                        {network.name}
                      </button>
                    </td>
                    <td>{TYPE_LABEL.get(network.type) ?? network.type}</td>
                    <td className="mono">{network.bridge || "-"}</td>
                    <td>{network.vlan_id ?? "-"}</td>
                    <td>
                      <span className="mono">{network.subnet || "-"}</span>
                      {network.gateway ? (
                        <div className="muted">网关 {network.gateway}</div>
                      ) : null}
                      {network.dns_servers ? (
                        <div className="muted">DNS {network.dns_servers}</div>
                      ) : null}
                    </td>
                    <td>
                      {network.dhcp_enabled ? (
                        <span className="mono">
                          {network.dhcp_start ?? "-"} ~{" "}
                          {network.dhcp_end ?? "-"}
                        </span>
                      ) : (
                        "未启用"
                      )}
                    </td>
                    <td>
                      {network.is_default ? (
                        <StatusBadge status="默认" />
                      ) : null}
                      {network.is_management ? (
                        <StatusBadge status="管理网" />
                      ) : null}
                      <StatusBadge
                        status={network.is_usable ? "可用" : "禁用"}
                      />
                    </td>
                    <td>
                      <span
                        className="truncate cell-desc"
                        title={network.description || undefined}
                      >
                        {network.description || "-"}
                      </span>
                    </td>
                    <td className="col-actions">
                      {canManage ? (
                        <div className="row-actions">
                          <button
                            className="action sm"
                            onClick={() => startEdit(network)}
                          >
                            编辑
                          </button>
                          <button
                            className="action sm danger"
                            onClick={() => setDeleting(network)}
                          >
                            删除
                          </button>
                        </div>
                      ) : (
                        "-"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </Card>
      ) : null}
      {selectedNetwork ? (
        <Drawer
          title={selectedNetwork.name}
          onClose={() => setSelectedNetwork(null)}
        >
          <div className="banner banner-info">
            此记录为已登记配置；真实运行状态和最后同步时间尚未由 Agent 采集。
          </div>
          <dl className="info-grid">
            <dt>网络类型</dt>
            <dd>{selectedNetwork.type}</dd>
            <dt>网桥 / VLAN</dt>
            <dd>
              {selectedNetwork.bridge || "—"} / {selectedNetwork.vlan_id ?? "—"}
            </dd>
            <dt>子网</dt>
            <dd>{selectedNetwork.subnet || "—"}</dd>
            <dt>网关</dt>
            <dd>{selectedNetwork.gateway || "—"}</dd>
            <dt>DHCP 配置</dt>
            <dd>
              {selectedNetwork.dhcp_enabled
                ? `${selectedNetwork.dhcp_start} – ${selectedNetwork.dhcp_end}`
                : "未启用"}
            </dd>
            <dt>配置更新时间</dt>
            <dd>{new Date(selectedNetwork.updated_at).toLocaleString()}</dd>
            <dt>当前列表关联实例</dt>
            <dd>
              {
                instances.filter(
                  (vm) => vm.network_name === selectedNetwork.name,
                ).length
              }
            </dd>
          </dl>
          <p className="muted">
            节点范围、网络 UUID 和多节点同步状态尚未提供。
          </p>
        </Drawer>
      ) : null}
      {deleting ? (
        <ConfirmOperationModal
          target={deleting.name}
          operation="删除网络记录"
          description="仅删除平台网络记录，不拆除宿主机网桥和 DHCP 服务。后端会拒绝删除仍被虚拟机引用的网络。"
          busy={busy}
          error={error}
          onCancel={() => setDeleting(null)}
          onConfirm={() => void remove(deleting)}
        />
      ) : null}
    </>
  );
}
