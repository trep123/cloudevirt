import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import {
  Card,
  ErrorBanner,
  StatusBadge,
  describeError,
  formatTime,
  EmptyState,
} from "../components/ui";
import { PageHeader } from "../components/ConsoleUI";
import { Icon } from "../components/icons";
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
  const [mode, setMode] = useState<"library" | "create" | "publish">("library"),
    [search, setSearch] = useState("");
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
    setMode("library");
  }

  function startEdit(template: Template) {
    setMode("create");
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
    <div className="templates-page">
      <PageHeader
        title="规格模板"
        description="统一资源规格与交付标准，让每一次部署都有据可循。"
      >
        <button className="action" onClick={() => void reload()}>
          <Icon name="refresh" size={15} />
          刷新
        </button>
        {canManage && (
          <button
            className="action primary"
            onClick={() => {
              resetForm();
              setMode("create");
            }}
          >
            <Icon name="plus" size={16} />
            新建模板
          </button>
        )}
      </PageHeader>
      <div className="template-overview">
        <div>
          <span className="overview-icon">
            <Icon name="template" size={21} />
          </span>
          <div>
            <span>当前列表模板</span>
            <strong>
              {templates.length}
              <small> 个</small>
            </strong>
          </div>
        </div>
        <div>
          <span className="overview-icon">
            <Icon name="cluster" size={21} />
          </span>
          <div>
            <span>公开可用</span>
            <strong>
              {templates.filter((t) => t.is_public).length}
              <small> 个</small>
            </strong>
          </div>
        </div>
        <div>
          <span className="overview-icon">
            <Icon name="users" size={21} />
          </span>
          <div>
            <span>定向授权用户</span>
            <strong>
              {new Set(templates.flatMap((t) => t.assigned_users || [])).size}
              <small> 位</small>
            </strong>
          </div>
        </div>
        <div className="template-overview-note">
          <Icon name="audit" size={18} />
          <span>
            管理员配置
            <br />
            <strong>按授权交付</strong>
          </span>
        </div>
      </div>
      <div className="template-tabs" role="tablist" aria-label="模板工作区">
        <button
          role="tab"
          aria-selected={mode === "library"}
          onClick={() => setMode("library")}
        >
          <Icon name="template" size={16} />
          模板库
        </button>
        {canManage && (
          <>
            <button
              role="tab"
              aria-selected={mode === "create"}
              onClick={() => setMode("create")}
            >
              <Icon name="settings" size={16} />
              {editing ? "编辑规格" : "资源规格"}
            </button>
            <button
              role="tab"
              aria-selected={mode === "publish"}
              onClick={() => setMode("publish")}
            >
              <Icon name="play" size={15} />
              发布部署版本
            </button>
          </>
        )}
      </div>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      {canManage ? (
        <div className="template-create-layout" hidden={mode !== "create"}>
          <Card
            title={editing ? `编辑模板：${editing.name}` : "定义资源规格"}
            description="设置基础资源与使用范围，再发布可部署的版本。"
            className="template-editor-card"
          >
            <form className="inline spec-form" onSubmit={submit}>
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
              <div className="field-wide template-access-panel">
                <h4>分配给用户</h4>
                <p className="muted">
                  关闭“公开模板”后，仅所选用户可以查看和使用已发布版本。此分配不会授予硬件修改权限。
                </p>
                <input
                  placeholder="搜索授权用户名"
                  value={userSearch}
                  onChange={(e) => setUserSearch(e.target.value)}
                />
                <p>已选择 {form.assigned_users.length} 位用户</p>
                <div className="infra-form template-user-options">
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
          <aside className="template-summary">
            <span className="summary-eyebrow">配置预览</span>
            <h3>{form.name || "未命名模板"}</h3>
            <p>规格会作为新建实例的默认资源配置。</p>
            <dl>
              <div>
                <dt>
                  <Icon name="cpu" size={16} />
                  处理器
                </dt>
                <dd>
                  {form.vcpu}
                  <small> vCPU</small>
                </dd>
              </div>
              <div>
                <dt>
                  <Icon name="memory" size={16} />
                  内存
                </dt>
                <dd>
                  {form.memory / 1024}
                  <small> GiB</small>
                </dd>
              </div>
              <div>
                <dt>
                  <Icon name="disk" size={16} />
                  系统盘
                </dt>
                <dd>
                  {form.disk}
                  <small> GiB</small>
                </dd>
              </div>
            </dl>
            <div className="summary-access">
              <Icon name={form.is_public ? "cluster" : "key"} size={17} />
              <div>
                <strong>{form.is_public ? "公开可用" : "定向分配"}</strong>
                <p>
                  {form.is_public
                    ? "所有有创建权限的用户可使用"
                    : `已选择 ${form.assigned_users.length} 位用户`}
                </p>
              </div>
            </div>
            <p className="summary-footnote">
              <Icon name="info" size={14} />
              配额和节点容量会在实际部署时再次校验。
            </p>
          </aside>
        </div>
      ) : null}
      {canManage && (
        <div hidden={mode !== "publish"}>
          <DeploymentTemplateEditor templates={templates} />
        </div>
      )}
      <div hidden={mode !== "library"}>
        <Card
          title="模板库"
          description="集中管理可复用的规格与授权范围。"
          className="template-library"
          extra={
            <label className="template-search">
              <Icon name="search" size={15} />
              <input
                aria-label="搜索模板"
                placeholder="搜索名称或说明"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
          }
        >
          {templates.length === 0 ? (
            <EmptyState
              icon="template"
              title="建立你的第一套资源标准"
              description="先定义规格与使用范围，再关联镜像、磁盘和网络，发布为可部署版本。"
              action={
                canManage ? (
                  <button
                    className="action primary"
                    onClick={() => setMode("create")}
                  >
                    <Icon name="plus" size={15} />
                    定义资源规格
                  </button>
                ) : undefined
              }
            />
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
                  {templates.length > 0 &&
                    !templates.some((t) =>
                      (t.name + " " + t.description)
                        .toLowerCase()
                        .includes(search.toLowerCase()),
                    ) && (
                      <tr>
                        <td colSpan={8}>
                          <EmptyState
                            icon="search"
                            title="没有匹配的模板"
                            description="尝试使用其他名称或说明关键字。"
                          />
                        </td>
                      </tr>
                    )}
                  {templates
                    .filter((t) =>
                      (t.name + " " + t.description)
                        .toLowerCase()
                        .includes(search.toLowerCase()),
                    )
                    .map((template) => (
                      <tr key={template.id}>
                        <td>
                          <div className="hardware-device-cell">
                            <span className="device-glyph">
                              <Icon name="template" size={18} />
                            </span>
                            <div>
                              <strong>{template.name}</strong>
                              <small>规格 #{template.id}</small>
                            </div>
                          </div>
                        </td>
                        <td>{template.vcpu}</td>
                        <td>{template.memory_mib} MiB</td>
                        <td>{template.disk_gib} GiB</td>
                        <td>
                          <StatusBadge
                            status={template.is_public ? "公开" : "定向分配"}
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
      </div>
    </div>
  );
}
