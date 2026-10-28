import { useState } from "react";
import type { CurrentUser } from "../../types";
import { UsersPage } from "../../pages/UsersPage";
import { PageHeader } from "../../components/ConsoleUI";
import { RolesPage } from "./RolesPage";
export function UsersAndRolesPage({ user }: { user: CurrentUser }) {
  const [tab, setTab] = useState(
    location.pathname.endsWith("/roles") ? "角色" : "用户",
  );
  const permissions = user.permissions;
  return (
    <>
      <PageHeader
        title="用户与权限"
        description="账号生命周期、批量导入导出、角色权限与节点范围"
      />
      <nav className="detail-tabs">
        {[
          ...(permissions.includes("accounts.manage_user") ? ["用户"] : []),
          ...(permissions.includes("accounts.manage_role") ? ["角色"] : []),
        ].map((value) => (
          <button
            key={value}
            className={tab === value ? "active" : ""}
            onClick={() => setTab(value)}
          >
            {value}
          </button>
        ))}
      </nav>
      {tab === "用户" ? <UsersPage /> : <RolesPage />}
    </>
  );
}
