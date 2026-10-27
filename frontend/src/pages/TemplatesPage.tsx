import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBanner, describeError, formatTime } from "../components/ui";
import type { Template } from "../types";

export function TemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [vcpu, setVcpu] = useState(2);
  const [memory, setMemory] = useState(2048);
  const [disk, setDisk] = useState(20);

  const reload = useCallback(async () => {
    try {
      setTemplates((await api.templates()).results);
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }, []);

  useEffect(() => { void reload(); }, [reload]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.createTemplate({ name, vcpu, memory_mib: memory, disk_gib: disk, description });
      setNotice(`模板 ${name} 已创建`);
      setName("");
      setDescription("");
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(tpl: Template) {
    if (!window.confirm(`确认删除模板 ${tpl.name}？`)) return;
    try {
      await api.deleteTemplate(tpl.id);
      await reload();
    } catch (err) {
      setError(describeError(err));
    }
  }

  return (
    <>
      <div className="page-head"><h2>模板</h2><button className="action" onClick={() => void reload()}>刷新</button></div>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      <Card title="创建模板">
        <form className="inline" onSubmit={submit}>
          <label>名称<input value={name} onChange={(e) => setName(e.target.value)} placeholder="standard-4c4g" required /></label>
          <label>vCPU<input type="number" min={1} max={64} value={vcpu} onChange={(e) => setVcpu(Number(e.target.value))} /></label>
          <label>内存(MiB)<input type="number" min={128} value={memory} onChange={(e) => setMemory(Number(e.target.value))} /></label>
          <label>系统盘(GiB)<input type="number" min={1} value={disk} onChange={(e) => setDisk(Number(e.target.value))} /></label>
          <label>说明<input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="可选" /></label>
          <button className="action primary" type="submit" disabled={busy}>{busy ? "提交中…" : "创建"}</button>
        </form>
      </Card>
      <Card title={`共 ${templates.length} 个模板`}>
        {templates.length === 0 ? <Empty text="暂无模板" /> : (
          <table>
            <thead><tr><th>名称</th><th>vCPU</th><th>内存</th><th>磁盘</th><th>说明</th><th>创建时间</th><th>操作</th></tr></thead>
            <tbody>
              {templates.map((tpl) => (
                <tr key={tpl.id}>
                  <td><strong>{tpl.name}</strong></td>
                  <td>{tpl.vcpu}</td>
                  <td>{tpl.memory_mib} MiB</td>
                  <td>{tpl.disk_gib} GiB</td>
                  <td>{tpl.description || "-"}</td>
                  <td>{formatTime(tpl.created_at)}</td>
                  <td><button className="action danger" onClick={() => void remove(tpl)}>删除</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
