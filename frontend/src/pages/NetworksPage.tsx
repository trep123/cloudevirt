import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { NetworkTopology } from "../components/NetworkTopology";
import { Card, Empty, ErrorBanner, StatusBadge, describeError } from "../components/ui";
import { can } from "../permissions";
import type { CurrentUser, Instance, InstanceInterface, Network } from "../types";

const NETWORK_TYPES = [
  { value: "LIBVIRT_NETWORK", label: "libvirt 网络" },
  { value: "BRIDGE", label: "Linux 网桥" },
  { value: "OVS", label: "Open vSwitch 网桥" },
];

const TYPE_LABEL = new Map(NETWORK_TYPES.map((item) => [item.value, item.label]));

type NetworkForm = {
  name: string;
  type: string;
  bridge: string;
  vlan: string;
  is_default: boolean;
  is_management: boolean;
  description: string;
};

const EMPTY_FORM: NetworkForm = {
  name: "",
  type: "LIBVIRT_NETWORK",
  bridge: "",
  vlan: "",
  is_default: false,
  is_management: false,
  description: "",
};

export function NetworksPage({ user }: { user: CurrentUser }) {
  const [networks, setNetworks] = useState<Network[]>([]);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [interfaces, setInterfaces] = useState<Record<number, InstanceInterface[]>>({});
  const [view, setView] = useState<"list" | "topology">("list");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<NetworkForm>(EMPTY_FORM);
  const [editing, setEditing] = useState<Network | null>(null);

  const canManage = can(user, "networks.manage_network");

  const reload = useCallback(async () => {
    try {
      const [networkPage, instancePage] = await Promise.all([api.networks(), api.instances()]);
      setNetworks(networkPage.results);
      setInstances(instancePage.results);
      const running = instancePage.results.filter((instance) => instance.observed_state === "RUNNING");
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
    setForm(EMPTY_FORM);
    setEditing(null);
  }

  function startEdit(network: Network) {
    setEditing(network);
    setForm({
      name: network.name,
      type: network.type,
      bridge: network.bridge,
      vlan: network.vlan_id == null ? "" : String(network.vlan_id),
      is_default: network.is_default,
      is_management: network.is_management,
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
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(network: Network) {
    if (!window.confirm(`确认删除网络 ${network.name}？已接入该网络的实例不会被自动修改。`)) return;
    setError(null);
    setNotice(null);
    try {
      await api.deleteNetwork(network.id);
      setNotice(`网络 ${network.name} 已删除`);
      if (editing?.id === network.id) resetForm();
      await reload();
    } catch (err) {
      setError(describeError(err));
    }
  }

  return (
    <>
      <div className="page-head">
        <h2>网络白名单</h2>
        <div className="actions">
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
          <button className="action" onClick={() => void reload()}>刷新</button>
        </div>
      </div>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      {canManage ? (
        <Card title={editing ? `编辑网络：${editing.name}` : "登记网络"}>
          <form className="inline" onSubmit={submit}>
            <label>名称<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="app-net" required /></label>
            <label>类型
              <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                {NETWORK_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </label>
            <label>{form.type === "OVS" ? "OVS 网桥" : "桥接设备"}
              <input
                value={form.bridge}
                onChange={(e) => setForm({ ...form, bridge: e.target.value })}
                placeholder={form.type === "OVS" ? "ovsbr0" : "br0"}
                required={form.type !== "LIBVIRT_NETWORK"}
              />
            </label>
            <label>VLAN<input type="number" min={1} max={4094} value={form.vlan} onChange={(e) => setForm({ ...form, vlan: e.target.value })} placeholder="可选" /></label>
            <label>说明<input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="可选" /></label>
            <label className="check"><input type="checkbox" checked={form.is_default} onChange={(e) => setForm({ ...form, is_default: e.target.checked })} /> 默认网络</label>
            <label className="check"><input type="checkbox" checked={form.is_management} onChange={(e) => setForm({ ...form, is_management: e.target.checked })} /> 管理网</label>
            <button className="action primary" type="submit" disabled={busy}>{busy ? "提交中…" : editing ? "保存" : "登记"}</button>
            {editing ? <button className="action" type="button" onClick={resetForm}>取消</button> : null}
          </form>
          <p className="muted">
            管理网禁止接入虚拟机；默认网络与管理网不能同时勾选。OVS 网络需先在宿主机创建对应 OVS 网桥，
            创建虚拟机时会注入 openvswitch 虚拟端口并按 VLAN 打标签。
          </p>
        </Card>
      ) : null}
      {view === "topology" ? (
        <Card title="网络与接口拓扑">
          <NetworkTopology networks={networks} instances={instances} interfaces={interfaces} />
        </Card>
      ) : null}
      {view === "list" ? (
      <Card title={`共 ${networks.length} 个网络`}>
        {networks.length === 0 ? (
          <Empty text={canManage ? "尚未登记网络，请先在上方登记节点上已验证的网络。" : "尚未登记网络。"} />
        ) : (
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>类型</th>
                <th>桥接</th>
                <th>VLAN</th>
                <th>属性</th>
                <th>说明</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {networks.map((network) => (
                <tr key={network.id}>
                  <td><strong>{network.name}</strong></td>
                  <td>{TYPE_LABEL.get(network.type) ?? network.type}</td>
                  <td className="mono">{network.bridge || "-"}</td>
                  <td>{network.vlan_id ?? "-"}</td>
                  <td>
                    {network.is_default ? <StatusBadge status="默认" /> : null}
                    {network.is_management ? <StatusBadge status="管理网" /> : null}
                    <StatusBadge status={network.is_usable ? "可用" : "禁用"} />
                  </td>
                  <td>{network.description || "-"}</td>
                  <td className="actions">
                    {canManage ? (
                      <>
                        <button className="action" onClick={() => startEdit(network)}>编辑</button>
                        <button className="action danger" onClick={() => void remove(network)}>删除</button>
                      </>
                    ) : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      ) : null}
    </>
  );
}
