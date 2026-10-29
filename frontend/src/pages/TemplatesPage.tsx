import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import {
  Card,
  Empty,
  ErrorBanner,
  StatusBadge,
  describeError,
  formatTime,
} from "../components/ui";
import { PageHeader } from "../components/ConsoleUI";
import { can } from "../permissions";
import { DeploymentTemplateEditor } from "../features/vms/DeploymentTemplateEditor";
import type { CurrentUser, Template, User } from "../types";

type TemplateForm = {
  assigned_users: number[];
  name: string;
  description: string;
  vcpu: number;
  memory: number;
  disk: number;
  is_public: boolean;
};

const EMPTY_FORM: TemplateForm = {
  assigned_users: [],
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
  const [users, setUsers] = useState<User[]>([]),
    [userSearch, setUserSearch] = useState("");

  const canManage =
    user.console_scope === "admin" && can(user, "templates.add_template");
  useEffect(() => {
    if (!canManage) return;
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
  }, [userSearch, canManage]);

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
      assigned_users: template.assigned_users || [],
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
      assigned_users: form.assigned_users,
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
      <PageHeader
        title="规格模板"
        description="预设 vCPU、内存与磁盘组合，创建虚拟机时可快速套用"
      >
        <button className="action" onClick={() => void reload()}>
          刷新
        </button>
      </PageHeader>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      {canManage ? (
        <Card title={editing ? `编辑模板：${editing.name}` : "创建模板"}>
          <form className="inline" onSubmit={submit}>
            <label>
              名称
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="standard-4c4g"
                required
              />
            </label>
            <label>
              vCPU
              <input
                type="number"
                min={1}
                max={64}
                value={form.vcpu}
                onChange={(e) =>
                  setForm({ ...form, vcpu: Number(e.target.value) })
                }
              />
            </label>
            <label>
              内存(MiB)
              <input
                type="number"
                min={128}
                value={form.memory}
                onChange={(e) =>
                  setForm({ ...form, memory: Number(e.target.value) })
                }
              />
            </label>
            <label>
              系统盘(GiB)
              <input
                type="number"
                min={1}
                value={form.disk}
                onChange={(e) =>
                  setForm({ ...form, disk: Number(e.target.value) })
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
                placeholder="可选"
              />
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={form.is_public}
                onChange={(e) =>
                  setForm({ ...form, is_public: e.target.checked })
                }
              />{" "}
              公开模板
            </label>
            <div className="field-wide">
              <h4>分配给用户</h4>
              <p className="muted">
                关闭“公开模板”后，仅所选用户可以查看和使用已发布版本。此分配不会授予硬件修改权限。
              </p>
              <input
                placeholder="搜索授权用户名"
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
              />
              <p>已选择用户 ID：{form.assigned_users.join(", ") || "无"}</p>
              <div className="infra-form">
                {users.map((u) => (
                  <label className="check" key={u.id}>
                    <input
                      type="checkbox"
                      checked={form.assigned_users.includes(u.id)}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          assigned_users: e.target.checked
                            ? [...form.assigned_users, u.id]
                            : form.assigned_users.filter((id) => id !== u.id),
                        })
                      }
                    />
                    {u.username} · #{u.id}
                  </label>
                ))}
              </div>
              <p className="muted">
                显示当前搜索前 100 项，其他用户可按用户名定位。
              </p>
            </div>
            <button className="action primary" type="submit" disabled={busy}>
              {busy ? "提交中…" : editing ? "保存" : "创建"}
            </button>
            {editing ? (
              <button className="action" type="button" onClick={resetForm}>
                取消
              </button>
            ) : null}
          </form>
        </Card>
      ) : null}
      {canManage && <DeploymentTemplateEditor templates={templates} />}
      <Card title={`共 ${templates.length} 个模板`}>
        {templates.length === 0 ? (
          <Empty text="暂无模板" />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>vCPU</th>
                  <th>内存</th>
                  <th>磁盘</th>
                  <th>可见性</th>
                  <th>说明</th>
                  <th>创建时间</th>
                  <th className="col-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                {templates.map((template) => (
                  <tr key={template.id}>
                    <td>
                      <strong>{template.name}</strong>
                    </td>
                    <td>{template.vcpu}</td>
                    <td>{template.memory_mib} MiB</td>
                    <td>{template.disk_gib} GiB</td>
                    <td>
                      <StatusBadge
                        status={template.is_public ? "公开" : "私有"}
                      />
                    </td>
                    <td>
                      <span
                        className="truncate cell-desc"
                        title={template.description || undefined}
                      >
                        {template.description || "-"}
                      </span>
                    </td>
                    <td>{formatTime(template.created_at)}</td>
                    <td className="actions">
                      {canManage ? (
                        <>
                          <button
                            className="action"
                            onClick={() => startEdit(template)}
                          >
                            编辑
                          </button>
                          <button
                            className="action danger"
                            onClick={() => void remove(template)}
                          >
                            删除
                          </button>
                        </>
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
    </>
  );
}
