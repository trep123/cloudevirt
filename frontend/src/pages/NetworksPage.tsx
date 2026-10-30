import type { TopologyVM as Instance } from "../features/networks/topologyModel";
import { useCallback, useEffect, useState } from "react";

import { newRequestId } from "../utils/requestId";
import { api } from "../api";
import { NetworkTopology } from "../components/NetworkTopology";
import { BridgeCreator } from "../features/networks/BridgeCreator";
import {
  Drawer,
  ConfirmOperationModal,
  PageHeader,
  TaskProgressDrawer,
} from "../components/ConsoleUI";
import { validateAddress } from "../features/networks/validateAddress";
import {
  Card,
  Empty,
  ErrorBanner,
  StatusBadge,
  describeError,
} from "../components/ui";
import { can } from "../permissions";
import type { CurrentUser, InstanceInterface, Network } from "../types";

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
  const [showBridge, setShowBridge] = useState(false);
  const [networkStep, setNetworkStep] = useState(0);
  const [deleting, setDeleting] = useState<Network | null>(null);
  const [selectedNetwork, setSelectedNetwork] = useState<Network | null>(null);

  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [connection, setConnection] = useState<{
      vm: Instance;
      network: Network;
      key: string;
    } | null>(null),
    [connectionTask, setConnectionTask] = useState<string | null>(null),
    [truncated, setTruncated] = useState(false);
  const canConnect =
    can(user, "instances.connect_network_instance") ||
    (user.console_scope === "admin" && can(user, "instances.change_instance"));
  const canManage =
    user.console_scope === "admin" && can(user, "networks.manage_network");

  const reload = useCallback(async () => {
    try {
      const topology = await api.request<{
        networks: Network[];
        instances: Instance[];
        interfaces: Record<number, InstanceInterface[]>;
        truncated: boolean;
      }>("/networks/topology");
      setNetworks(topology.networks);
      setInstances(topology.instances);
      setInterfaces(topology.interfaces);
      setTruncated(topology.truncated);
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);
  useEffect(() => {
    if (
      !networks.some(
        (n) =>
          n.managed &&
          ["PENDING", "CREATING"].includes(n.provisioning_status || ""),
      )
    )
      return;
    const timer = setInterval(() => {
      if (!document.hidden) void reload();
    }, 5000);
    return () => clearInterval(timer);
  }, [networks, reload]);

  useEffect(() => {
    if (view !== "topology") return;
    const timer = setInterval(() => {
      if (!document.hidden) void reload();
    }, 15000);
    return () => clearInterval(timer);
  }, [view, reload]);
  async function connect() {
    if (!connection || busy) return;
    setBusy(true);
    setConnectionError(null);
    try {
      const result = await api.request<{ task: { id: string } }>(
        `/instances/${connection.vm.id}/hardware`,
        {
          method: "POST",
          headers: { "Idempotency-Key": connection.key },
          body: JSON.stringify({
            operation: "nic-add",
            network_name: connection.network.name,
            model: "virtio",
            ...(connection.vm.observed_state === "RUNNING"
              ? { live: true }
              : {}),
          }),
        },
      );
      setConnection(null);
      setConnectionTask(result.task.id);
    } catch (e) {
      setConnectionError(describeError(e));
    } finally {
      setBusy(false);
    }
  }
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
        title={canManage ? "网络管理" : "网络连接"}
        description={
          canManage
            ? "创建节点桥接网络，管理已有网络、VLAN 与地址规划"
            : "查看已授权网络，将自己的虚拟机连接到可用业务网络"
        }
      >
        {canManage && user.console_scope === "admin" && (
          <button
            className="action primary"
            onClick={() => setShowBridge(true)}
          >
            创建桥接网络
          </button>
        )}
        {canManage ? (
          <button
            className="action"
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
      {showBridge && (
        <BridgeCreator
          onClose={() => setShowBridge(false)}
          onCreated={(id) => {
            setShowBridge(false);
            setNotice(`创建任务已提交：${id}，网桥核验成功后才可供虚拟机使用`);
            void reload();
          }}
        />
      )}
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
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
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
                    onChange={(e) => setForm({ ...form, type: e.target.value })}
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
                    onChange={(e) => setForm({ ...form, vlan: e.target.value })}
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
          {truncated && (
            <p className="muted">
              当前展示最多 300 台授权虚拟机，请结合节点筛选查看。
            </p>
          )}
          <NetworkTopology
            networks={networks}
            instances={instances}
            interfaces={interfaces}
            editable={canConnect && !busy && !connectionTask}
            onConnect={(vm, network) => {
              setError(null);
              setConnectionError(null);
              setConnection({ vm, network, key: newRequestId() });
            }}
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
                    <th>节点 / 创建状态</th>
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
                      <td>
                        {network.node ? `节点 #${network.node}` : "全局登记"}
                        <small className="muted" style={{ display: "block" }}>
                          {network.managed
                            ? {
                                READY: "已核验",
                                PENDING: "等待创建",
                                CREATING: "创建中",
                                FAILED: "创建失败",
                              }[network.provisioning_status || ""] || "待核对"
                            : "已有网络记录"}
                          {network.uplink ? ` · ${network.uplink}` : ""}
                        </small>
                        {network.last_error && (
                          <small className="danger-text">
                            {network.last_error}
                          </small>
                        )}
                        {canManage &&
                          network.managed &&
                          network.provisioning_status === "FAILED" && (
                            <button
                              className="action sm"
                              onClick={() => {
                                void api
                                  .request(
                                    `/networks/${network.id}/provision`,
                                    { method: "POST", body: "{}" },
                                  )
                                  .then(() => reload())
                                  .catch((e) => setError(describeError(e)));
                              }}
                            >
                              核对并重试
                            </button>
                          )}
                      </td>
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
                              disabled={network.managed}
                              title={
                                network.managed
                                  ? "托管网桥需先在节点安全解除物理网卡，不能仅删除登记记录"
                                  : undefined
                              }
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
            {selectedNetwork.managed
              ? "此网桥由节点网络服务创建并保存；创建状态表示上次执行结果，实时链路状态请以节点接口检测为准。"
              : "此记录为已登记配置；真实运行状态和最后同步时间尚未由 Agent 采集。"}
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
                instances.filter((vm) =>
                  (interfaces[vm.id] || []).some(
                    (nic) => nic.source === selectedNetwork.name,
                  ),
                ).length
              }
            </dd>
          </dl>
          <p className="muted">
            节点范围、网络 UUID 和多节点同步状态尚未提供。
          </p>
        </Drawer>
      ) : null}
      {connection && (
        <ConfirmOperationModal
          target={`${connection.vm.name} → ${connection.network.name}`}
          operation={
            connection.vm.observed_state === "RUNNING"
              ? "热接入网络（新增 VirtIO 网卡）"
              : "接入网络（新增 VirtIO 网卡）"
          }
          description="保留现有网卡，新增独立 MAC 的网卡并同步持久配置。运行中接入需要节点与客体驱动支持；存在快照时需先处理一致性。任务成功并回读确认后更新连线。"
          busy={busy}
          error={connectionError}
          onCancel={() => {
            if (!busy) setConnection(null);
          }}
          onConfirm={() => void connect()}
        />
      )}
      {connectionTask && (
        <TaskProgressDrawer
          id={connectionTask}
          onClose={() => {
            setConnectionTask(null);
            void reload();
          }}
        />
      )}
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
