import { useEffect, useState } from "react";
import { api } from "../../api";
import { UsersPage } from "../../pages/UsersPage";
import { PageHeader } from "../../components/ConsoleUI";
import { Card, ErrorBanner, describeError } from "../../components/ui";
type Role = { id: number; name: string; permissions: string[] };
export function UsersAndRolesPage() {
  const [tab, setTab] = useState("用户"),
    [roles, setRoles] = useState<Role[]>([]),
    [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .request<{ results: Role[] }>("/console/roles")
      .then((p) => setRoles(p.results))
      .catch((e) => setError(describeError(e)));
  }, []);
  return (
    <>
      <PageHeader
        title="用户与权限"
        description="管理平台账号及服务端角色权限，项目与配额扩展待接入"
      />
      <nav className="detail-tabs">
        {["用户", "角色"].map((t) => (
          <button
            key={t}
            className={tab === t ? "active" : ""}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </nav>
      {tab === "用户" ? (
        <UsersPage />
      ) : (
        <>
          <ErrorBanner message={error} />
          <Card title="角色权限（只读）">
            {roles.map((r) => (
              <details className="role-detail" key={r.id}>
                <summary>
                  {r.name} · {r.permissions.length} 项权限
                </summary>
                <div className="perm-grid">
                  {r.permissions.map((p) => (
                    <span className="badge badge-muted" key={p}>
                      {p}
                    </span>
                  ))}
                </div>
              </details>
            ))}
            <p className="muted">角色编辑以当前服务端权限矩阵为准。</p>
          </Card>
        </>
      )}
    </>
  );
}
