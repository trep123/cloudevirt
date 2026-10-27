import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBanner, StatusBadge, describeError, formatTime } from "../components/ui";
import type { Image, Instance, Network, Node, Template } from "../types";

const ACTIONS: { key: string; label: string; danger?: boolean }[] = [
  { key: "start", label: "启动" },
  { key: "shutdown", label: "关机" },
  { key: "reboot", label: "重启" },
  { key: "force-stop", label: "强制停止", danger: true },
];

export function InstancesPage() {
  const [instances, setInstances] = useState<Instance[]>([]);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [images, setImages] = useState<Image[]>([]);
  const [networks, setNetworks] = useState<Network[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [name, setName] = useState("");
  const [nodeId, setNodeId] = useState("");
  const [imageId, setImageId] = useState("");
  const [networkName, setNetworkName] = useState("");
  const [vcpu, setVcpu] = useState(2);
  const [memory, setMemory] = useState(2048);
  const [disk, setDisk] = useState(20);
  const [templateId, setTemplateId] = useState("");

  function applyTemplate(id: number | null) {
    if (!id) { setTemplateId(""); return; }
    const tpl = templates.find((t) => t.id === id);
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
    } catch (err) {
      setError(describeError(err));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

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
    try {
      const result = await api.instanceAction(instance.id, action);
      setNotice(result.task ? `操作已提交，任务 ${result.task.id.slice(0, 8)}` : "实例已处于该状态");
      await reload();
    } catch (err) {
      setError(describeError(err));
    }
  }

  async function remove(instance: Instance) {
    const purge = window.confirm(`删除 ${instance.name}？\n\n点击“确定”同时删除磁盘，点击“取消”保留磁盘。`);
    if (purge && !window.confirm("再次确认：磁盘将被永久删除。")) return;
    try {
      await api.deleteInstance(instance.id, purge);
      setNotice(`删除任务已提交（${purge ? "含磁盘" : "保留磁盘"}）`);
      await reload();
    } catch (err) {
      setError(describeError(err));
    }
  }

  return (
    <>
      <div className="page-head">
        <h2>虚拟机</h2>
        <button className="action" onClick={() => void reload()}>刷新</button>
      </div>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      <Card title="创建虚拟机">
        <form className="inline" onSubmit={submit}>
          <label>
            模板
            <select value={templateId} onChange={(e) => applyTemplate(Number(e.target.value) || null)}>
              <option value="">自定义</option>
              {templates.map((tpl) => <option key={tpl.id} value={tpl.id}>{tpl.name} ({tpl.vcpu}C{tpl.memory_mib}M{tpl.disk_gib}G)</option>)}
            </select>
          </label>
          <label>
            名称
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="vm-demo-01" required />
          </label>
          <label>
            节点
            <select value={nodeId} onChange={(e) => setNodeId(e.target.value)} required>
              <option value="">选择节点</option>
              {nodes.map((node) => (
                <option key={node.id} value={node.id} disabled={!node.is_schedulable}>
                  {node.name}（{node.status}）
                </option>
              ))}
            </select>
          </label>
          <label>
            镜像
            <select value={imageId} onChange={(e) => setImageId(e.target.value)} required>
              <option value="">选择镜像</option>
              {images.map((image) => (
                <option key={image.id} value={image.id}>
                  {image.name}（{image.format}）
                </option>
              ))}
            </select>
          </label>
          <label>
            网络
            <select value={networkName} onChange={(e) => setNetworkName(e.target.value)}>
              <option value="">不接入</option>
              {networks.map((network) => (
                <option key={network.id} value={network.name}>
                  {network.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            vCPU
            <input type="number" min={1} value={vcpu} onChange={(e) => setVcpu(Number(e.target.value))} />
          </label>
          <label>
            内存(MiB)
            <input type="number" min={128} value={memory} onChange={(e) => setMemory(Number(e.target.value))} />
          </label>
          <label>
            系统盘(GiB)
            <input type="number" min={1} value={disk} onChange={(e) => setDisk(Number(e.target.value))} />
          </label>
          <button className="action primary" type="submit" disabled={busy}>
            {busy ? "提交中…" : "创建"}
          </button>
        </form>
      </Card>
      <Card title={`共 ${instances.length} 台虚拟机`}>
        {instances.length === 0 ? (
          <Empty text="暂无虚拟机" />
        ) : (
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>状态</th>
                <th>规格</th>
                <th>节点 / 镜像</th>
                <th>观测时间</th>
                <th>操作</th>
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
                      <div className="muted">
                        {instance.last_error_code}: {instance.last_error_message}
                      </div>
                    ) : null}
                  </td>
                  <td>
                    {instance.vcpu} vCPU / {instance.memory_mib} MiB / {instance.disk_gib} GiB
                  </td>
                  <td>
                    {instance.node_name}
                    <div className="muted">{instance.image_name}</div>
                  </td>
                  <td>
                    {formatTime(instance.observed_state_updated_at)}
                    {instance.observed_state_is_stale ? <div className="muted">数据已过期</div> : null}
                  </td>
                  <td>
                    {ACTIONS.map((action) => (
                      <button
                        key={action.key}
                        className={`action${action.danger ? " danger" : ""}`}
                        onClick={() => void runAction(instance, action.key)}
                      >
                        {action.label}
                      </button>
                    ))}
                    <button className="action danger" onClick={() => void remove(instance)}>
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
