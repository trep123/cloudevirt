import { useEffect, useState } from "react";
import { api } from "../../api";
import { ConfirmOperationModal, TaskProgressDrawer } from "../../components/ConsoleUI";
import { ErrorBanner, describeError } from "../../components/ui";
import { Icon } from "../../components/icons";

type Inventory = {
  system?: {
    os: { firmware: string; loader: string; type: { machine: string; arch: string }; boot: { device: string }[] | null };
    cpu: { mode: string; model: string; topology: { sockets: number; cores: number; threads: number } | null };
  };
  vcpu: number;
  memory_mib: number;
  disks: unknown[];
  nics: unknown[];
};
type Options = { autostart: boolean; requires_shutdown: boolean };

export function VmOptionsPanel({ id, admin, storagePool }: { id: number; admin: boolean; storagePool?: string }) {
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [options, setOptions] = useState<Options | null>(null);
  const [autostart, setAutostart] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [task, setTask] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let alive = true;
    setError(null);
    Promise.all([
      api.request<Inventory>(`/instances/${id}/hardware${storagePool ? `?storage_pool=${encodeURIComponent(storagePool)}` : ""}`),
      api.request<Options>(`/instances/${id}/options`),
    ])
      .then(([hardware, current]) => {
        if (!alive) return;
        setInventory(hardware);
        setOptions(current);
        setAutostart(current.autostart);
      })
      .catch((err) => alive && setError(describeError(err)));
    return () => { alive = false; };
  }, [id, storagePool, revision]);

  async function save(confirmed = false) {
    if (!admin || busy || !options) return;
    if (!confirmed) { setConfirm(true); return; }
    setBusy(true);
    setError(null);
    try {
      const result = await api.request<{ task: { id: string } | null; autostart: boolean }>(`/instances/${id}/options`, {
        method: "POST",
        body: JSON.stringify({ autostart }),
      });
      setConfirm(false);
      if (result.task) setTask(result.task.id);
      else setOptions({ ...options, autostart: result.autostart });
    } catch (err) {
      setError(describeError(err));
    } finally { setBusy(false); }
  }

  const system = inventory?.system;
  const firmware = system?.os.firmware || (system?.os.loader ? "uefi" : "bios");
  const boot = system?.os.boot?.map((entry) => entry.device).join(" → ") || "由节点或设备级顺序决定";
  return <section className="vm-options-panel">
    <header className="hardware-panel-head">
      <div className="hardware-title">
        <span className="hardware-icon"><Icon name="settings" size={20} /></span>
        <div><h3>虚拟机配置</h3><p>查看节点已生效配置，管理启动选项与设备策略。</p></div>
      </div>
      <button className="action sm" onClick={() => setRevision((v) => v + 1)} disabled={busy}><Icon name="refresh" size={14} />刷新</button>
    </header>
    <ErrorBanner message={error} />
    {(!inventory || !options) && !error && <p className="muted">正在读取节点实际配置…</p>}
    {inventory && options && <>
      <div className="hardware-kpis vm-options-kpis">
        <div><span>处理器</span><strong>{inventory.vcpu}<small> vCPU</small></strong></div>
        <div><span>内存</span><strong>{inventory.memory_mib / 1024}<small> GiB</small></strong></div>
        <div><span>设备</span><strong>{inventory.disks.length + inventory.nics.length}<small> 个</small></strong></div>
      </div>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>配置项</th><th>当前生效值</th><th>管理位置</th></tr></thead><tbody>
        <tr><td>固件</td><td>{firmware.toUpperCase()}</td><td>创建后固定；含 Secure Boot、TPM 的系统盘请通过克隆重建。</td></tr>
        <tr><td>机型 / 架构</td><td>{system ? `${system.os.type.machine || "节点默认"} · ${system.os.type.arch || "未返回"}` : "未返回"}</td><td>由节点和创建配置确定</td></tr>
        <tr><td>CPU 模式 / 拓扑</td><td>{system?.cpu.mode || system?.cpu.model || "节点默认"}{system?.cpu.topology ? ` · ${system.cpu.topology.sockets} 插槽 × ${system.cpu.topology.cores} 核 × ${system.cpu.topology.threads} 线程` : ""}</td><td>硬件页可调整 CPU、内存</td></tr>
        <tr><td>启动顺序</td><td>{boot}</td><td>挂载 ISO 后优先从光驱启动；在磁盘页管理光驱</td></tr>
        <tr><td>显示与剪贴板</td><td>由虚拟显卡与客体驱动决定</td><td>硬件页的“显示与交互”</td></tr>
      </tbody></table></div>
      <section className="vm-option-editor">
        <h4>启动选项</h4>
        <p className="muted">以下选项由异步任务写入 libvirt，任务成功后才更新平台记录。</p>
        <label className="check"><input type="checkbox" checked={autostart} disabled={!admin || busy || !!task} onChange={(event) => setAutostart(event.target.checked)} />宿主机启动后自动启动此虚拟机</label>
        <p className="muted">此选项不会立即启动或关闭虚拟机。{admin ? "" : "仅平台管理员可以修改。"}</p>
        {admin && <button className="action" disabled={busy || !!task || autostart === options.autostart} onClick={() => void save()}>{busy ? "正在提交…" : "保存启动选项"}</button>}
      </section>
    </>}
    {confirm && <ConfirmOperationModal target={`虚拟机 #${id}`} operation={autostart ? "启用开机自启" : "关闭开机自启"} description="此操作只修改宿主机重启后的自动启动策略，不改变当前运行状态。" busy={busy} error={error} onCancel={() => setConfirm(false)} onConfirm={() => void save(true)} />}
    {task && <TaskProgressDrawer id={task} onClose={() => { setTask(null); setRevision((v) => v + 1); }} />}
  </section>;
}
