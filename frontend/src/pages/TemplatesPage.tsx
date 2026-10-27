import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBanner, StatusBadge, describeError, formatTime } from "../components/ui";
import { can } from "../permissions";
import type { CurrentUser, Template } from "../types";

type TemplateForm = {
  name: string;
  description: string;
  vcpu: number;
  memory: number;
  disk: number;
  is_public: boolean;
};

const EMPTY_FORM: TemplateForm = {
  name: "",
  description: "",
  vcpu: 2,
  memory: 2048,
  disk: 20,
  is_public: true,
};

export function TemplatesPage({ user }: { user: CurrentUser }) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<TemplateForm>(EMPTY_FORM);
  const [editing, setEditing] = useState<Template | null>(null);

  const canManage = can(user, "templates.add_template");

  const reload = useCallback(async () => {
    try {
      setTemplates((await api.templates()).results);
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

  function startEdit(template: Template) {
    setEditing(template);
    setForm({
      name: template.name,
      description: template.description,
      vcpu: template.vcpu,
      memory: template.memory_mib,
      disk: template.disk_gib,
      is_public: template.is_public,
    });
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    const payload = {
      name: form.name,
      description: form.description,
      vcpu: form.vcpu,
      memory_mib: form.memory,
      disk_gib: form.disk,
      is_public: form.is_public,
    };
    try {
      if (editing) {
        await api.updateTemplate(editing.id, payload);
        setNotice(`模板 ${form.name} 已更新`);
      } else {
        await api.createTemplate(payload);
        setNotice(`模板 ${form.name} 已创建`);
      }
      resetForm();
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(template: Template) {
    if (!window.confirm(`确认删除模板 ${template.name}？`)) return;
    setError(null);
    setNotice(null);
    try {
      await api.deleteTemplate(template.id);
      setNotice(`模板 ${template.name} 已删除`);
      if (editing?.id === template.id) resetForm();
      await reload();
    } catch (err) {
      setError(describeError(err));
    }
  }

  return (
    <>
      <div className="page-head">
        <h2>规格模板</h2>
        <button className="action" onClick={() => void reload()}>刷新</button>
      </div>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      {canManage ? (
        <Card title={editing ? `编辑模板：${editing.name}` : "创建模板"}>
          <form className="inline" onSubmit={submit}>
            <label>名称<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="standard-4c4g" required /></label>
            <label>vCPU<input type="number" min={1} max={64} value={form.vcpu} onChange={(e) => setForm({ ...form, vcpu: Number(e.target.value) })} /></label>
            <label>内存(MiB)<input type="number" min={128} value={form.memory} onChange={(e) => setForm({ ...form, memory: Number(e.target.value) })} /></label>
            <label>系统盘(GiB)<input type="number" min={1} value={form.disk} onChange={(e) => setForm({ ...form, disk: Number(e.target.value) })} /></label>
            <label>说明<input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="可选" /></label>
            <label className="check"><input type="checkbox" checked={form.is_public} onChange={(e) => setForm({ ...form, is_public: e.target.checked })} /> 公开模板</label>
            <button className="action primary" type="submit" disabled={busy}>{busy ? "提交中…" : editing ? "保存" : "创建"}</button>
            {editing ? <button className="action" type="button" onClick={resetForm}>取消</button> : null}
          </form>
        </Card>
      ) : null}
      <Card title={`共 ${templates.length} 个模板`}>
        {templates.length === 0 ? <Empty text="暂无模板" /> : (
          <table>
            <thead><tr><th>名称</th><th>vCPU</th><th>内存</th><th>磁盘</th><th>可见性</th><th>说明</th><th>创建时间</th><th>操作</th></tr></thead>
            <tbody>
              {templates.map((template) => (
                <tr key={template.id}>
                  <td><strong>{template.name}</strong></td>
                  <td>{template.vcpu}</td>
                  <td>{template.memory_mib} MiB</td>
                  <td>{template.disk_gib} GiB</td>
                  <td><StatusBadge status={template.is_public ? "公开" : "私有"} /></td>
                  <td>{template.description || "-"}</td>
                  <td>{formatTime(template.created_at)}</td>
                  <td className="actions">
                    {canManage ? (
                      <>
                        <button className="action" onClick={() => startEdit(template)}>编辑</button>
                        <button className="action danger" onClick={() => void remove(template)}>删除</button>
                      </>
                    ) : "-"}
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
