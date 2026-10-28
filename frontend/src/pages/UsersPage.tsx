import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBanner, StatusBadge, describeError, formatTime } from "../components/ui";
import { PageHeader } from "../components/ConsoleUI";
import { ROLE_OPTIONS } from "../roles";
import type { AuditEvent, User } from "../types";

export function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<User | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [credential, setCredential] = useState<{ username: string; password: string } | null>(null);

  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("Operator");

  const reload = useCallback(async () => {
    try {
      setUsers((await api.users()).results);
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
      await api.createUser({
        username,
        email: email || undefined,
        display_name: displayName || undefined,
        password: password || undefined,
        roles: [role],
      });
      setNotice(`用户 ${username} 已创建`);
      setUsername(""); setDisplayName(""); setEmail(""); setPassword("");
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive(user: User) {
    try {
      await api.updateUser(user.id, { is_active: !user.is_active });
      await reload();
    } catch (err) { setError(describeError(err)); }
  }

  async function changeRole(user: User, newRole: string) {
    try {
      await api.updateUser(user.id, { roles: [newRole] });
      await reload();
    } catch (err) { setError(describeError(err)); }
  }

  async function resetPassword(user: User) {
    if (!window.confirm(`确认重置 ${user.username} 的密码？旧密码将立即失效。`)) return;
    setError(null);
    setNotice(null);
    try {
      const result = await api.resetUserPassword(user.id);
      setCredential(result);
      setNotice(`已重置 ${result.username} 的密码，临时口令仅显示一次`);
      await reload();
    } catch (err) { setError(describeError(err)); }
  }

  async function showDetail(user: User) {
    setSelected(user);
    setAudit([]);
    try {
      const result = await api.userAudit(user.id);
      setAudit(result.results);
    } catch (err) { setError(describeError(err)); }
  }

  return (
    <>
      <PageHeader title="用户管理" description="平台账号、角色分配与登录状态">
        <button className="action" onClick={() => void reload()}>刷新</button>
      </PageHeader>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      {credential ? (
        <div className="banner banner-info">
          临时口令（关闭后不可再查看）：<strong>{credential.username}</strong> / <code>{credential.password}</code>
          <button className="action" onClick={() => setCredential(null)}>我已记录</button>
        </div>
      ) : null}
      <Card title="创建用户">
        <form className="inline" onSubmit={submit}>
          <label>用户名<input value={username} onChange={(e) => setUsername(e.target.value)} required /></label>
          <label>显示名<input value={displayName} onChange={(e) => setDisplayName(e.target.value)} /></label>
          <label>邮箱<input value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>初始密码<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="留空则强制改密" /></label>
          <label>角色
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLE_OPTIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </label>
          <button className="action primary" type="submit" disabled={busy}>{busy ? "提交中…" : "创建"}</button>
        </form>
      </Card>
      <Card title={`共 ${users.length} 个用户`}>
        {users.length === 0 ? <Empty text="暂无用户" /> : (
          <table>
            <thead><tr><th>用户名</th><th>显示名</th><th>角色</th><th>状态</th><th>需改密</th><th>最近登录</th><th>操作</th></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td><strong>{u.username}</strong>{u.email ? <div className="muted">{u.email}</div> : null}</td>
                  <td>{u.display_name || "-"}</td>
                  <td>
                    <select value={u.roles[0] || ""} onChange={(e) => void changeRole(u, e.target.value)}>
                      <option value="" disabled>未分配</option>
                      {ROLE_OPTIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                    </select>
                  </td>
                  <td><StatusBadge status={u.is_active ? "ACTIVE" : "DISABLED"} /></td>
                  <td>{u.must_change_password ? <span className="muted">是</span> : "-"}</td>
                  <td>{formatTime(u.last_login)}</td>
                  <td className="actions">
                    <button className="action" onClick={() => void showDetail(u)}>详情</button>
                    <button className="action" onClick={() => void resetPassword(u)}>重置密码</button>
                    <button className="action" onClick={() => void toggleActive(u)}>{u.is_active ? "停用" : "启用"}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {selected ? (
        <Card title={`用户详情：${selected.username}`}>
          <p className="muted">权限矩阵（共 {selected.permissions.length} 项）</p>
          <div className="perm-grid">
            {selected.permissions.map((p) => <span key={p} className="perm-tag">{p}</span>)}
          </div>
          <h3>最近审计事件</h3>
          {audit.length === 0 ? <Empty text="暂无审计记录" /> : (
            <table>
              <thead><tr><th>时间</th><th>动作</th><th>对象</th><th>详情</th></tr></thead>
              <tbody>
                {audit.map((e) => (
                  <tr key={e.id}>
                    <td>{formatTime(e.created_at)}</td>
                    <td className="mono">{e.action}</td>
                    <td className="mono">{e.target_type}:{e.target_id}</td>
                    <td className="mono">{JSON.stringify(e.details)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      ) : null}
    </>
  );
}
