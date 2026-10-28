import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api";
import { Card, ErrorBanner, describeError } from "../../components/ui";
type Row = {
  row?: number;
  username?: string;
  status: string;
  errors?: Record<string, unknown>;
  values?: Record<string, string>;
};
type Batch = {
  id: string;
  kind: string;
  state: string;
  strict: boolean;
  preview?: Row[];
  results: Row[];
  total: number;
  task_id: string | null;
  download_ready: boolean;
  expires_at: string;
};
export async function downloadAccountFile(path: string) {
  const response = await fetch("/api/v1" + path, {
    credentials: "same-origin",
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(response.status, payload?.error || null);
  }
  const url = URL.createObjectURL(await response.blob()),
    anchor = document.createElement("a");
  anchor.href = url;
  anchor.download =
    /filename="([^"]+)"/.exec(
      response.headers.get("Content-Disposition") || "",
    )?.[1] || "users.csv";
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const fields = [
  "username",
  "display_name",
  "role_codes",
  "status",
  "node_ids",
  "quota_instances",
  "quota_vcpu",
  "quota_memory_mib",
  "quota_disk_gib",
  "created_at",
  "updated_at",
  "last_login",
];
const labels: Record<string, string> = {
  DRAFT: "预校验完成",
  PENDING: "等待后台处理",
  RUNNING: "执行中",
  SUCCEEDED: "处理完成",
  PARTIAL: "部分成功",
  FAILED: "处理失败",
  CANCELLED: "已取消",
  EXPIRED: "已过期",
  CREATE: "待新增",
  UPDATE: "待更新",
  ERROR: "失败",
  SUCCESS: "成功",
};
export function AccountBatchPanel({
  selected,
  filters,
  onImported,
  permissions,
}: {
  selected: number[];
  filters: { search: string; role: string; active: string };
  onImported: () => void;
  permissions: string[];
}) {
  const [open, setOpen] = useState(false),
    [kind, setKind] = useState("import"),
    [file, setFile] = useState<File | null>(null),
    [mode, setMode] = useState("create"),
    [strict, setStrict] = useState(false),
    [format, setFormat] = useState("csv"),
    [scope, setScope] = useState("filtered"),
    [columns, setColumns] = useState(fields),
    [batch, setBatch] = useState<Batch | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  const alive = useRef(true),
    done = useRef("");
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    if (!batch || !["PENDING", "RUNNING"].includes(batch.state)) return;
    let cancelled = false,
      timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api.request<Batch>(`/users/batches/${batch.id}`);
        if (cancelled) return;
        setBatch(next);
        if (
          ["SUCCEEDED", "PARTIAL"].includes(next.state) &&
          next.kind === "import" &&
          done.current !== next.id
        ) {
          done.current = next.id;
          onImported();
        }
        if (["PENDING", "RUNNING"].includes(next.state))
          timer = setTimeout(() => void poll(), document.hidden ? 15000 : 2000);
      } catch (error) {
        if (!cancelled) {
          setError(describeError(error));
          timer = setTimeout(() => void poll(), 15000);
        }
      }
    };
    timer = setTimeout(() => void poll(), 1000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [batch?.id, batch?.state, onImported]);
  async function submit() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      let body: FormData | string;
      if (kind === "import") {
        if (!file) throw Error("请选择 CSV 或 XLSX 文件");
        body = new FormData();
        body.append("kind", "import");
        body.append("mode", mode);
        body.append("strict", String(strict));
        body.append("file", file);
      } else {
        if (scope === "selected" && !selected.length)
          throw Error("请先勾选用户");
        body = JSON.stringify({
          kind: "export",
          format,
          fields: columns,
          ...(scope === "selected"
            ? { ids: selected }
            : scope === "filtered"
              ? { filters }
              : {}),
        });
      }
      const result = await api.request<Batch>("/users/batches", {
        method: "POST",
        body,
      });
      if (alive.current) setBatch(result);
    } catch (error) {
      if (alive.current) setError(describeError(error));
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function confirm() {
    if (
      !batch ||
      busy ||
      !window.confirm(
        `确认执行 ${batch.total} 行导入？角色整体替换，空单元格保留原值。${batch.strict ? "失败整批回滚。" : "有效行提交，错误行不修改。"}`,
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      setBatch(
        await api.request<Batch>(`/users/batches/${batch.id}`, {
          method: "POST",
        }),
      );
    } catch (error) {
      setError(describeError(error));
    } finally {
      setBusy(false);
    }
  }
  async function download(path: string) {
    try {
      await downloadAccountFile(path);
    } catch (error) {
      setError(describeError(error));
    }
  }
  const active = !!batch && ["PENDING", "RUNNING"].includes(batch.state),
    canImport = permissions.includes("accounts.import_user"),
    canExport = permissions.includes("accounts.export_user");
  return (
    <Card title="批量导入与导出">
      <button className="action" onClick={() => setOpen(!open)}>
        {open ? "收起批量工具" : "展开批量工具"}
      </button>
      {open && (
        <>
          <ErrorBanner message={error} />
          <div className="toolbar" style={{ marginTop: 16 }}>
            <select
              aria-label="批量操作"
              value={kind}
              disabled={busy || active}
              onChange={(e) => {
                setKind(e.target.value);
                setBatch(null);
              }}
            >
              <option value="import">导入用户</option>
              <option value="export">导出用户</option>
            </select>
            {kind === "import" ? (
              <>
                <input
                  aria-label="用户导入文件"
                  type="file"
                  accept=".csv,.xlsx"
                  disabled={busy || active}
                  onChange={(e) => {
                    setFile(e.target.files?.[0] || null);
                    setBatch(null);
                  }}
                />
                <select
                  aria-label="导入模式"
                  value={mode}
                  disabled={busy || active}
                  onChange={(e) => {
                    setMode(e.target.value);
                    setBatch(null);
                  }}
                >
                  <option value="create">仅新增</option>
                  <option value="update">仅更新</option>
                  <option value="upsert">新增并更新</option>
                </select>
                <label>
                  <input
                    type="checkbox"
                    checked={strict}
                    disabled={busy || active}
                    onChange={(e) => {
                      setStrict(e.target.checked);
                      setBatch(null);
                    }}
                  />
                  严格模式
                </label>
                {["csv", "xlsx"].map((value) => (
                  <button
                    key={value}
                    className="action"
                    disabled={!canImport}
                    onClick={() =>
                      void download("/users/import-template?format=" + value)
                    }
                  >
                    {value.toUpperCase()} 模板
                  </button>
                ))}
              </>
            ) : (
              <>
                <select
                  aria-label="导出范围"
                  value={scope}
                  disabled={busy || active}
                  onChange={(e) => setScope(e.target.value)}
                >
                  <option value="filtered">当前筛选结果</option>
                  <option value="selected">
                    已勾选 {selected.length} 个用户
                  </option>
                  <option value="all">全部用户</option>
                </select>
                <select
                  aria-label="导出格式"
                  value={format}
                  disabled={busy || active}
                  onChange={(e) => setFormat(e.target.value)}
                >
                  <option value="csv">CSV</option>
                  <option value="xlsx">XLSX</option>
                </select>
              </>
            )}
            <button
              className="action primary"
              disabled={
                busy || active || (kind === "import" ? !canImport : !canExport)
              }
              onClick={() => void submit()}
            >
              {busy
                ? "提交中…"
                : kind === "import"
                  ? "上传并预校验"
                  : "创建导出任务"}
            </button>
          </div>
          {kind === "export" && (
            <div className="perm-grid">
              {[...fields, "email", "remark"].map((field) => (
                <label key={field}>
                  <input
                    type="checkbox"
                    checked={columns.includes(field)}
                    disabled={
                      busy ||
                      active ||
                      (["email", "remark"].includes(field) &&
                        !permissions.includes("accounts.export_sensitive_user"))
                    }
                    onChange={(e) =>
                      setColumns(
                        e.target.checked
                          ? [...columns, field]
                          : columns.filter((value) => value !== field),
                      )
                    }
                  />
                  {field}
                  {["email", "remark"].includes(field) ? "（敏感）" : ""}
                </label>
              ))}
            </div>
          )}
          <p className="muted">
            CSV 使用 UTF-8；最多 1000 行、5 MB。角色和节点 ID
            用分号分隔；空单元格保留原值，邮箱/备注用 __CLEAR__ 清空，节点 []
            表示无节点、__CLEAR__ 表示继承。内存 MiB，磁盘 GiB。
          </p>
          <p className="muted">
            禁止密码、超级用户标记、Token
            和项目字段。新账号为待激活，请重置密码并单独启用。预览与文件 30
            分钟后失效。
          </p>
          {batch && (
            <section>
              <h3>
                {labels[batch.state] || batch.state} · {batch.id.slice(0, 8)}
              </h3>
              {batch.state === "DRAFT" && (
                <button
                  className="action primary"
                  disabled={
                    busy ||
                    (batch.strict &&
                      batch.preview?.some((row) => row.status === "ERROR")) ||
                    !batch.preview?.some((row) => row.status !== "ERROR")
                  }
                  onClick={() => void confirm()}
                >
                  确认执行导入
                </button>
              )}
              {(batch.kind === "import" || batch.download_ready) && (
                <button
                  className="action"
                  onClick={() =>
                    void download(`/users/batches/${batch.id}/download`)
                  }
                >
                  {batch.kind === "import" ? "下载逐行结果" : "下载导出文件"}
                </button>
              )}
              <button
                className="action"
                disabled={busy || ["PENDING", "RUNNING"].includes(batch.state)}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await api.request(`/users/batches/${batch.id}`, {
                      method: "DELETE",
                    });
                    setBatch(null);
                    setError(null);
                  } catch (error) {
                    setError(describeError(error));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                清理批次 / 放弃预览
              </button>
              <p className="muted">
                到期：{new Date(batch.expires_at).toLocaleString()}；界面展示前
                100 条，完整结果请下载。
              </p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>行</th>
                      <th>用户名</th>
                      <th>结果</th>
                      <th>预览 / 错误</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(batch.preview || batch.results)
                      .slice(0, 100)
                      .map((row, index) => (
                        <tr key={row.row || index}>
                          <td>{row.row || "—"}</td>
                          <td>{row.username || row.values?.username || "—"}</td>
                          <td>{labels[row.status] || row.status}</td>
                          <td
                            style={{
                              maxWidth: 500,
                              whiteSpace: "normal",
                              overflowWrap: "anywhere",
                            }}
                          >
                            {JSON.stringify(row.errors || row.values || row)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </Card>
  );
}
