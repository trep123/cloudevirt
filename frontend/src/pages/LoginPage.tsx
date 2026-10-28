import { useState } from "react";

import { api } from "../api";
import type { CurrentUser } from "../types";
import { describeError } from "../components/ui";

export function LoginPage({
  onLogin,
}: {
  onLogin: (user: CurrentUser) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLogin(await api.login(username, password));
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <div className="login">
        <h1>CloudVirt</h1>
        <p>虚拟机管理台，请使用平台账号登录。</p>
        <form onSubmit={submit}>
          <label>
            用户名
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
            />
          </label>
          <label>
            密码
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          {error ? <div className="banner banner-error">{error}</div> : null}
          <button className="action primary" type="submit" disabled={busy}>
            {busy ? "登录中…" : "登录"}
          </button>
        </form>
        <p className="login-footer">QEMU / KVM 虚拟化管理平台</p>
      </div>
    </div>
  );
}

export function ChangePasswordGate({
  user,
  onDone,
  onLogout,
}: {
  user: CurrentUser;
  onDone: () => void;
  onLogout: () => void;
}) {
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.changePassword(oldPassword, newPassword);
      onDone();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <div className="login">
        <h1>修改初始密码</h1>
        <p>{user.username}，首次登录必须修改密码后才能使用平台功能。</p>
        <form onSubmit={submit}>
          <label>
            当前密码
            <input
              type="password"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
            />
          </label>
          <label>
            新密码（至少 12 位）
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
          </label>
          {error ? <div className="banner banner-error">{error}</div> : null}
          <button className="action primary" type="submit" disabled={busy}>
            {busy ? "提交中…" : "确认修改"}
          </button>
          <button className="action block" type="button" onClick={onLogout}>
            退出登录
          </button>
        </form>
      </div>
    </div>
  );
}
