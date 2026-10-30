import { useState } from "react";

import { api } from "../api";
import { PageHeader } from "../components/ConsoleUI";
import { Icon } from "../components/icons";
import { ErrorBanner, describeError } from "../components/ui";
import { roleLabel } from "../roles";
import type { CurrentUser } from "../types";
import "./profile-page.css";

export function ProfilePage({
  user,
  onLogout,
}: {
  user: CurrentUser;
  onLogout: () => void;
}) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPasswords, setShowPasswords] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function savePassword(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(false);
    if (newPassword.length < 12) {
      setError("新密码至少需要 12 位字符");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("两次输入的新密码不一致");
      return;
    }
    if (newPassword === currentPassword) {
      setError("新密码不能与当前密码相同");
      return;
    }
    setBusy(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setSuccess(true);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  const passwordType = showPasswords ? "text" : "password";
  return (
    <div className="profile-page">
      <PageHeader
        title="个人设置"
        description="查看账号身份，维护登录密码与当前会话。"
      />
      <div className="profile-grid">
        <aside className="profile-identity card" aria-label="账号信息">
          <div className="profile-identity-top">
            <div className="profile-avatar" aria-hidden="true">
              {(user.display_name || user.username).slice(0, 1).toUpperCase()}
            </div>
            <div>
              <h3>{user.display_name || user.username}</h3>
              <p>@{user.username}</p>
            </div>
          </div>
          <div className="profile-identity-meta">
            <div>
              <span>账户类型</span>
              <strong>{user.console_scope === "admin" || user.roles.includes("Admin") ? "管理账户" : "用户账户"}</strong>
            </div>
            <div>
              <span>分配角色</span>
              <div className="profile-roles">
                {user.roles.length ? user.roles.map((role) => (
                  <span className="profile-role" key={role}>
                    {roleLabel(role)}
                  </span>
                )) : <strong>未分配角色</strong>}
              </div>
            </div>
            <div>
              <span>账号编号</span>
              <strong>#{user.id}</strong>
            </div>
          </div>
          <p className="profile-help">显示名称与角色由平台管理员统一维护。</p>
        </aside>

        <div className="profile-content">
          <section className="profile-panel card" aria-labelledby="profile-password-title">
            <div className="profile-panel-heading">
              <span className="profile-panel-icon" aria-hidden="true"><Icon name="key" size={17} /></span>
              <div>
                <h3 id="profile-password-title">登录密码</h3>
                <p>定期更新密码，修改后当前会话会保持登录。</p>
              </div>
            </div>
            <form onSubmit={savePassword} className="profile-password-form">
              <label>
                当前密码
                <input
                  type={passwordType}
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  required
                  disabled={busy}
                />
              </label>
              <div className="profile-password-columns">
                <label>
                  新密码
                  <input
                    type={passwordType}
                    autoComplete="new-password"
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    minLength={12}
                    required
                    disabled={busy}
                  />
                </label>
                <label>
                  确认新密码
                  <input
                    type={passwordType}
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    minLength={12}
                    required
                    disabled={busy}
                  />
                </label>
              </div>
              <div className="profile-password-hint">
                <span>至少 12 位；具体复杂度由服务端校验。</span>
                <label className="profile-show-passwords">
                  <input
                    type="checkbox"
                    checked={showPasswords}
                    onChange={(event) => setShowPasswords(event.target.checked)}
                  />
                  显示密码
                </label>
              </div>
              <ErrorBanner message={error} />
              {success && (
                <div className="profile-success" role="status">
                  密码已更新，当前会话仍可继续使用。
                </div>
              )}
              <div className="profile-form-actions">
                <button className="action primary" type="submit" disabled={busy}>
                  {busy ? "正在保存…" : "更新密码"}
                </button>
              </div>
            </form>
          </section>

          <section className="profile-panel profile-session card" aria-labelledby="profile-session-title">
            <div>
              <h3 id="profile-session-title">当前会话</h3>
              <p>退出登录将结束本浏览器会话及关联的远程控制台连接。</p>
            </div>
            <button className="action" type="button" onClick={onLogout}>
              退出当前账号
            </button>
          </section>
        </div>
      </div>
    </div>
  );
}
