import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { PageHeader, ConfirmOperationModal } from "../components/ConsoleUI";
import { ErrorBanner, describeError, formatTime, Card } from "../components/ui";
import { can } from "../permissions";
import {
  DeploymentTemplateEditor,
  type DeploymentVersion,
} from "../features/vms/DeploymentTemplateEditor";
import type { CurrentUser } from "../types";

export function TemplatesPage({ user }: { user: CurrentUser }) {
  const [versions, setVersions] = useState<DeploymentVersion[]>([]),
    [error, setError] = useState<string | null>(null),
    [loading, setLoading] = useState(true),
    [mode, setMode] = useState(false),
    [editing, setEditing] = useState<DeploymentVersion | null>(null),
    [search, setSearch] = useState(""),
    [removing, setRemoving] = useState<DeploymentVersion | null>(null),
    [busy, setBusy] = useState(false);
  const manage =
    user.console_scope === "admin" && can(user, "templates.add_template");
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const v = await api.request<{ results: DeploymentVersion[] }>(
        "/templates/deployments",
      );
      setVersions(v.results);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setLoading(false);
    }
  }, [manage]);
  useEffect(() => {
    void reload();
  }, [reload]);
  const filtered = versions.filter((v) =>
    `${v.template_name} v${v.version}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  return (
    <div className="templates-page">
      <PageHeader
        title="部署模板"
        description="模板库仅收录已发布的完整部署版本；用户选择模板后只需填写名称并指定网卡网络。"
      >
        <button
          className="action"
          onClick={() => void reload()}
          disabled={loading}
        >
          刷新
        </button>
        {manage && (
          <button
            className="action primary"
            onClick={() => {
              setEditing(null);
              setMode(true);
            }}
          >
            新建部署模板
          </button>
        )}
      </PageHeader>
      <ErrorBanner message={error} />
      {mode && manage ? (
        <>
          <button className="action" onClick={() => setMode(false)}>
            返回模板库
          </button>
          <DeploymentTemplateEditor
            key={editing?.id || "new"}
            editing={editing}
            onSaved={() => {
              setMode(false);
              setEditing(null);
              void reload();
            }}
          />
        </>
      ) : (
        <Card
          title="模板库"
          description="编辑与删除仅影响后续部署；已有虚拟机保持原配置。"
        >
          <input
            aria-label="搜索部署模板"
            placeholder="按模板名称或版本搜索"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {loading ? (
            <p role="status">正在读取部署模板…</p>
          ) : !filtered.length ? (
            <p className="empty">
              暂无匹配的已发布部署模板
              {manage
                ? "，请新建并发布完整部署配置。"
                : "，请联系管理员分配模板。"}
            </p>
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>部署模板 / 版本</th>
                    <th>计算资源</th>
                    <th>磁盘 / 网卡</th>
                    <th>版本创建时间</th>
                    {manage && <th>操作</th>}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((v) => (
                    <tr key={v.id}>
                      <td>
                        <strong>{v.template_name}</strong> · v{v.version}
                        <small className="muted">{v.description}</small>
                      </td>
                      <td>
                        {String(v.configuration.vcpu)} vCPU ·{" "}
                        {Number(v.configuration.memory_mib) / 1024} GiB
                      </td>
                      <td>
                        {String(v.configuration.disk_gib)} GiB 系统盘 ·{" "}
                        {
                          ((v.configuration.data_disks as unknown[]) || [])
                            .length
                        }{" "}
                        数据盘 ·{" "}
                        {1 +
                          (
                            (v.configuration
                              .additional_networks as unknown[]) || []
                          ).length}{" "}
                        网卡
                      </td>
                      <td>{formatTime(v.created_at)}</td>
                      {manage && (
                        <td>
                          <button
                            className="action sm"
                            onClick={() => {
                              setEditing(v);
                              setMode(true);
                            }}
                          >
                            编辑
                          </button>{" "}
                          <button
                            className="action sm danger"
                            onClick={() => setRemoving(v)}
                          >
                            删除
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
      {removing && (
        <ConfirmOperationModal
          target={`${removing.template_name} v${removing.version}`}
          operation="删除部署模板版本"
          description="从模板库移除并禁止新的部署；不会删除已创建虚拟机、磁盘或镜像，历史配置仍保留供追溯。"
          busy={busy}
          error={error}
          onCancel={() => {
            if (!busy) setRemoving(null);
          }}
          onConfirm={async () => {
            if (busy) return;
            setBusy(true);
            try {
              await api.request(`/template-versions/${removing.id}`, {
                method: "DELETE",
              });
              setRemoving(null);
              await reload();
            } catch (e) {
              setError(describeError(e));
            } finally {
              setBusy(false);
            }
          }}
        />
      )}
    </div>
  );
}
