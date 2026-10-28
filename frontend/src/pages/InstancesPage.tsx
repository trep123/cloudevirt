import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { VncConsole } from "../components/VncConsole";
import { Card, Empty, ErrorBanner, StatusBadge, describeError, formatTime } from "../components/ui";
import { can } from "../permissions";
import type { CurrentUser, Image, Instance, InstanceAddress, Network, Node, Template } from "../types";

const ACTIONS: { key: string; label: string; permission: string; danger?: boolean }[] = [
  { key: "start", label: "启动", permission: "instances.start_instance" },
  { key: "shutdown", label: "关机", permission: "instances.shutdown_instance" },
  { key: "reboot", label: "重启", permission: "instances.reboot_instance" },
  { key: "force-stop", label: "强制停止", permission: "instances.force_stop_instance", danger: true },
];

const ACTIVE_OPERATION_STATUSES = ["PENDING", "VALIDATING", "PREPARING", "CREATING", "VERIFYING"];

export function InstancesPage({ user }: { user: CurrentUser }) {
  const [instances, setInstances] = useState<Instance[]>([]);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [images, setImages] = useState<Image[]>([]);
  const [networks, setNetworks] = useState<Network[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [addresses, setAddresses] = useState<Record<number, InstanceAddress[]>>({});

  const [name, setName] = useState("");
  const [nodeId, setNodeId] = useState("");
  const [imageId, setImageId] = useState("");
  const [networkName, setNetworkName] = useState("");
  const [vcpu, setVcpu] = useState(2);
  const [memory, setMemory] = useState(2048);
  const [disk, setDisk] = useState(20);
  const [autostart, setAutostart] = useState(true);
  const [templateId, setTemplateId] = useState("");

  const canCreate = can(user, "instances.add_instance");
  const canDelete = can(user, "instances.delete_instance");
  const canDeleteDisk = can(user, "instances.delete_disk_instance");

  function applyTemplate(id: number | null) {
    if (!id) { setTemplateId(""); return; }
    const tpl = templates.find((item) => item.id === id);
    if (!tpl) return;
    setTemplateId(String(id));
    setVcpu(tpl.vcpu);
    setMemory(tpl.memory_mib);
    setDisk(tpl.disk_gib);
  }

  const reload = useCallback(async () => {
    try {
      const [instancePage, nodePage, imagePage, networkPage, templatePage] = await Promise.all([
        api.instances(),
        api.nodes(),
        api.images(),
        api.networks(),
        api.templates(),
      ]);
      setInstances(instancePage.results);
      setNodes(nodePage.results);
      setImages(imagePage.results.filter((image) => image.is_ready));
      setNetworks(networkPage.results.filter((network) => network.is_usable));
      setTemplates(templatePage.results);
      setError(null);
      const running = instancePage.results.filter((instance) => instance.observed_state === "RUNNING");
      if (running.length === 0) {
        setAddresses({});
      } else {
        void Promise.all(
          running.map(async (instance) => {
            try {
              const data = await api.instanceAddresses(instance.id);
              return [instance.id, data.addresses] as const;
            } catch {
              return [instance.id, []] as const;
            }
          }),
        ).then((entries) => setAddresses(Object.fromEntries(entries)));
      }
    } catch (err) {
      setError(describeError(err));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const hasActiveOperation = instances.some((instance) =>
    ACTIVE_OPERATION_STATUSES.includes(instance.operation_status),
  );
  const detail = detailId == null ? null : instances.find((instance) => instance.id === detailId) ?? null;

  useEffect(() => {
    if (!hasActiveOperation) return;
    const timer = window.setInterval(() => void reload(), 4000);
    return () => window.clearInterval(timer);
  }, [hasActiveOperation, reload]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api.createInstance({
        name,
        node: Number(nodeId),
        image: Number(imageId),
        vcpu,
        memory_mib: memory,
        disk_gib: disk,
        network_name: networkName,
        autostart,
      });
      setNotice(`已创建 ${result.instance.name}，任务 ${result.task.id.slice(0, 8)} 正在执行`);
      setName("");
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function runAction(instance: Instance, action: string) {
    if (action === "force-stop" && !window.confirm(`确认强制停止 ${instance.name}？该操作等同断电。`)) {
      return;
    }
    setError(null);
    setNotice(null);
    try {
      const result = await api.instanceAction(instance.id, action);
      setNotice(result.task ? `操作已提交，任务 ${result.task.id.slice(0, 8)}` : "实例已处于该状态");
      await reload();
    } catch (err) {
      setError(describeError(err));
    }
  }

  async function remove(instance: Instance) {
    if (!window.confirm(`确认删除 ${instance.name}？`)) return;
    const purge = canDeleteDisk && window.confirm("是否同时删除磁盘文件？选择取消则只注销实例并保留磁盘。");
    setError(null);
    setNotice(null);
    try {
      await api.deleteInstance(instance.id, purge);
      setNotice(`删除任务已提交（${purge ? "含磁盘" : "保留磁盘"}）`);
      if (detailId === instance.id) setDetailId(null);
      await reload();
    } catch (err) {
      setError(describeError(err));
    }
  }

  function renderAddresses(instance: Instance) {
    const list = addresses[instance.id] ?? [];
    if (list.length === 0) {
      return <span className="muted">{instance.observed_state === "RUNNING" ? "未获取" : "-"}</span>;
    }
    return (
      <div className="ip-list">
        {list.map((item) => (
          <span key={`${item.interface}-${item.address}`} className={`ip-tag ip-${item.protocol}`}>
            {item.protocol === "ipv6" ? "IPv6" : "IPv4"} {item.address}
          </span>
        ))}
      </div>
    );
  }

  return (
    <>
      <div className="page-head">
        <h2>虚拟机</h2>
        <button className="action" onClick={() => void reload()}>刷新</button>
      </div>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      {canCreate ? (
        <Card title="创建虚拟机">
          <form className="inline" onSubmit={submit}>
            <label>模板
              <select value={templateId} onChange={(e) => applyTemplate(Number(e.target.value) || null)}>
                <option value="">自定义</option>
                {templates.map((tpl) => <option key={tpl.id} value={tpl.id}>{tpl.name} ({tpl.vcpu}C{tpl.memory_mib}M{tpl.disk_gib}G)</option>)}
              </select>
            </label>
            <label>名称<input value={name} onChange={(e) => setName(e.target.value)} placeholder="vm-demo-01" required /></label>
            <label>节点
              <select value={nodeId} onChange={(e) => setNodeId(e.target.value)} required>
                <option value="">选择节点</option>
                {nodes.map((node) => (
                  <option key={node.id} value={node.id} disabled={!node.is_schedulable}>{node.name}（{node.status}）</option>
                ))}
              </select>
            </label>
            <label>镜像
              <select value={imageId} onChange={(e) => setImageId(e.target.value)} required>
                <option value="">选择镜像</option>
                {images.map((image) => <option key={image.id} value={image.id}>{image.name}（{image.format}）</option>)}
              </select>
            </label>
            <label>网络
              <select value={networkName} onChange={(e) => setNetworkName(e.target.value)}>
                <option value="">不接入</option>
                {networks.map((network) => <option key={network.id} value={network.name}>{network.name}</option>)}
              </select>
            </label>
            <label>vCPU<input type="number" min={1} value={vcpu} onChange={(e) => setVcpu(Number(e.target.value))} /></label>
            <label>内存(MiB)<input type="number" min={128} value={memory} onChange={(e) => setMemory(Number(e.target.value))} /></label>
            <label>系统盘(GiB)<input type="number" min={1} value={disk} onChange={(e) => setDisk(Number(e.target.value))} /></label>
            <label className="check"><input type="checkbox" checked={autostart} onChange={(e) => setAutostart(e.target.checked)} /> 创建后启动</label>
            <button className="action primary" type="submit" disabled={busy}>{busy ? "提交中…" : "创建"}</button>
          </form>
        </Card>
      ) : null}
      <Card title={`共 ${instances.length} 台虚拟机`}>
        {instances.length === 0 ? <Empty text="暂无虚拟机" /> : (
          <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>状态</th>
                <th>规格</th>
                <th>节点 / 镜像</th>
                <th>网络</th>
                <th>IP 地址</th>
                <th>观测时间</th>
                <th className="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              {instances.map((instance) => (
                <tr key={instance.id}>
                  <td>
                    <strong>{instance.name}</strong>
                    <div className="mono muted">{instance.libvirt_domain_name}</div>
                  </td>
                  <td>
                    <StatusBadge status={instance.observed_state} />
                    <div className="muted">任务：{instance.operation_status}</div>
                    {instance.last_error_message ? (
                      <div className="muted">{instance.last_error_code}: {instance.last_error_message}</div>
                    ) : null}
                  </td>
                  <td>{instance.vcpu} vCPU / {instance.memory_mib} MiB / {instance.disk_gib} GiB</td>
                  <td>{instance.node_name}<div className="muted">{instance.image_name}</div></td>
                  <td>{instance.network_name || "未接入"}</td>
                  <td>{renderAddresses(instance)}</td>
                  <td>
                    {formatTime(instance.observed_state_updated_at)}
                    {instance.observed_state_is_stale ? <div className="muted">数据已过期</div> : null}
                  </td>
                  <td className="actions">
                    {ACTIONS.filter((action) => can(user, action.permission)).map((action) => (
                      <button
                        key={action.key}
                        className={`action${action.danger ? " danger" : ""}`}
                        onClick={() => void runAction(instance, action.key)}
                      >
                        {action.label}
                      </button>
                    ))}
                    <button className="action" onClick={() => setDetailId(instance.id)}>详情</button>
                    {canDelete ? <button className="action danger" onClick={() => void remove(instance)}>删除</button> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </Card>
      {detail ? (
        <Card title={`虚拟机详情：${detail.name}`}>
          <div className="detail-panel">
            <h3>VNC 控制台</h3>
            {detail.observed_state === "RUNNING" ? (
              <VncConsole instanceId={detail.id} />
            ) : (
              <p className="muted">实例未运行，启动后可打开控制台。</p>
            )}
          </div>
          <div className="detail-panel">
            <h3>基本信息</h3>
            <p className="muted">
              UUID：<span className="mono">{detail.uuid}</span><br />
              节点：{detail.node_name} / 镜像：{detail.image_name} / 网络：{detail.network_name || "未接入"}<br />
              期望状态：{detail.desired_state} / 观测状态：{detail.observed_state} / 自动启动：{detail.autostart ? "是" : "否"}<br />
              创建时间：{formatTime(detail.created_at)} / 更新时间：{formatTime(detail.updated_at)}
            </p>
            <h3>IP 地址</h3>
            {renderAddresses(detail)}
          </div>
          <h3>磁盘</h3>
          {detail.disks.length === 0 ? <Empty text="无磁盘记录" /> : (
            <div className="table-scroll">
            <table>
              <thead><tr><th>文件名</th><th>角色</th><th>状态</th><th>容量</th><th>设备</th><th>路径</th></tr></thead>
              <tbody>
                {detail.disks.map((disk) => (
                  <tr key={disk.id}>
                    <td className="mono">{disk.name}</td>
                    <td>{disk.role}</td>
                    <td><StatusBadge status={disk.status} /></td>
                    <td>{disk.size_gib} GiB</td>
                    <td className="mono">{disk.target_dev}</td>
                    <td className="mono muted">{disk.relative_path}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
          {detail.last_error_message ? <div className="banner banner-error">{detail.last_error_code}: {detail.last_error_message}</div> : null}
          <button className="action" onClick={() => setDetailId(null)}>关闭</button>
        </Card>
      ) : null}
    </>
  );
}
