import { useEffect, useState } from "react";
import { api } from "../../api";
import { PageHeader } from "../../components/ConsoleUI";
import { ErrorBanner, describeError } from "../../components/ui";
import { infra, type Configuration } from "./client";
import { navigate } from "../../app/router";

export function SettingsPage() {
  const [config, setConfig] = useState<Configuration | null>(null);
  const [error, setError] = useState<string | null>(null),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true;
    infra
      .configuration()
      .then((c) => {
        if (live) {
          setConfig(c);
          setError(null);
        }
      })
      .catch((e) => {
        if (live) setError(describeError(e));
      });
    return () => {
      live = false;
    };
  }, [revision]);
  return (
    <>
      <PageHeader
        title="系统设置"
        description="配置即时生效；管理凭据和服务监听地址由部署配置管理，不通过浏览器暴露"
      >
        <button
          className="action"
          disabled={busy}
          onClick={() => {
            setMessage("");
            setRevision((x) => x + 1);
          }}
        >
          重新加载
        </button>
      </PageHeader>
      <ErrorBanner message={error} />
      {message ? (
        <p className="banner banner-info" role="status">
          {message}
        </p>
      ) : null}
      {!config ? (
        <p role="status">
          {error ? "配置加载失败，请重新加载。" : "正在加载配置…"}
        </p>
      ) : (
        <form
          className="card infra-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            setMessage("");
            try {
              const result = await api.request<Configuration>(
                "/admin/settings/",
                { method: "PUT", body: JSON.stringify(config) },
              );
              setConfig(result);
              setMessage(
                `配置已保存，版本 ${result.revision}。普通用户下一次创建虚拟机时使用新配额。`,
              );
            } catch (e) {
              setError(describeError(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          <h3>普通用户默认资源配额</h3>
          <p className="muted">
            每个账号分别计算总配置量。降低限额不会删除或停止已有资源；超额账号不能继续创建。
          </p>
          {(
            [
              ["instances", "虚拟机数量"],
              ["vcpu", "vCPU 总核数"],
              ["memory_mib", "内存总量（MiB）"],
              ["disk_gib", "磁盘总量（GiB）"],
            ] as const
          ).map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                required
                type="number"
                min={1}
                max={
                  key === "instances" || key === "vcpu" ? 1000000 : 2147483647
                }
                value={config.quota[key]}
                onChange={(e) =>
                  setConfig({
                    ...config,
                    quota: { ...config.quota, [key]: Number(e.target.value) },
                  })
                }
              />
            </label>
          ))}
          <h3>存储容量提示阈值</h3>
          <label>
            警告使用率（%）
            <input
              required
              type="number"
              min={1}
              max={99}
              value={config.storage_warning_percent}
              onChange={(e) =>
                setConfig({
                  ...config,
                  storage_warning_percent: Number(e.target.value),
                })
              }
            />
          </label>
          <label>
            高风险使用率（%）
            <input
              required
              type="number"
              min={config.storage_warning_percent + 1}
              max={100}
              value={config.storage_critical_percent}
              onChange={(e) =>
                setConfig({
                  ...config,
                  storage_critical_percent: Number(e.target.value),
                })
              }
            />
          </label>
          <button className="action primary" disabled={busy}>
            {busy ? "正在保存…" : "保存设置"}
          </button>
        </form>
      )}
      <section className="card">
        <h3>节点代理与认证</h3>
        <p>
          节点代理连接状态、版本和诊断信息由节点管理提供。账号密码和会话通过平台认证接口管理。
        </p>
        <div className="actions">
          <button className="action" onClick={() => navigate("/admin/nodes")}>
            管理节点代理
          </button>
          <button className="action" onClick={() => navigate("/admin/users")}>
            用户与角色
          </button>
          <button className="action" onClick={() => navigate("/admin/audit")}>
            配置变更审计
          </button>
        </div>
      </section>
    </>
  );
}
