import { useState } from "react";

import { api } from "../api";
import type { CurrentUser } from "../types";
import { describeError } from "../components/ui";

const FEATURES: { title: string; desc: string; icon: React.ReactNode }[] = [
  {
    title: "虚拟机全生命周期管理",
    desc: "创建、启停、快照与迁移，一处完成。",
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="4" width="18" height="12" rx="2" />
        <path d="M8 20h8M12 16v4" />
      </svg>
    ),
  },
  {
    title: "多节点集群与资源池",
    desc: "统一调度计算、存储与网络资源。",
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="3" width="18" height="6" rx="1.5" />
        <rect x="3" y="15" width="18" height="6" rx="1.5" />
        <path d="M7 6h.01M7 18h.01M12 9v6" />
      </svg>
    ),
  },
  {
    title: "浏览器内远程控制台",
    desc: "无需插件，即开即用的 VNC / WebRTC 访问。",
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M3 9h18M7 13l3 2-3 2M12 17h4" />
      </svg>
    ),
  },
];

function BrandMark() {
  return (
    <svg className="auth-logo" viewBox="0 0 40 40" aria-hidden="true">
      <defs>
        <linearGradient id="cv-logo-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6d9bff" />
          <stop offset="1" stopColor="#2557e6" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="11" fill="url(#cv-logo-g)" />
      <path
        d="M13 25.5a5 5 0 0 1 .6-9.96A7 7 0 0 1 27 16.5a4.5 4.5 0 0 1 0 9H13Z"
        fill="#fff"
        fillOpacity="0.95"
      />
    </svg>
  );
}

export function LoginPage({
  onLogin,
}: {
  onLogin: (user: CurrentUser) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

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
    <div className="auth-screen">
      <aside className="auth-brand">
        <div className="auth-brand-glow" aria-hidden="true" />
        <div className="auth-brand-inner">
          <div className="auth-brand-head">
            <BrandMark />
            <span className="auth-brand-name">CloudVirt</span>
          </div>
          <div className="auth-brand-copy">
            <h2>
              <span>统一管理您的</span> <span>QEMU / KVM 虚拟化集群</span>
            </h2>
            <p>面向企业的私有云虚拟化平台，稳定、安全、可观测。</p>
            <ul className="auth-features">
              {FEATURES.map((f) => (
                <li key={f.title}>
                  <span className="auth-feature-icon">{f.icon}</span>
                  <span>
                    <strong>{f.title}</strong>
                    <small>{f.desc}</small>
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <p className="auth-copyright">
            © {new Date().getFullYear()} CloudVirt · QEMU / KVM 虚拟化管理平台
          </p>
        </div>
      </aside>

      <main className="auth-main">
        <div className="auth-card">
          <h1>欢迎登录</h1>
          <p>虚拟机管理台，请使用平台账号登录。</p>
          <form onSubmit={submit}>
            <label>
              用户名
              <span className="auth-field">
                <svg className="auth-field-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="12" cy="8" r="4" />
                  <path d="M4 20a8 8 0 0 1 16 0" />
                </svg>
                <input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  placeholder="请输入用户名"
                />
              </span>
            </label>
            <label>
              密码
              <span className="auth-field">
                <svg className="auth-field-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <rect x="4" y="10" width="16" height="11" rx="2" />
                  <path d="M8 10V7a4 4 0 0 1 8 0v3" />
                </svg>
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  placeholder="请输入密码"
                />
                <button
                  type="button"
                  className="auth-toggle"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "隐藏密码" : "显示密码"}
                  aria-pressed={showPassword}
                  title={showPassword ? "隐藏密码" : "显示密码"}
                >
                  {showPassword ? (
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M3 3l18 18M10.6 5.1A10.4 10.4 0 0 1 12 5c6 0 9.5 7 9.5 7a17 17 0 0 1-3.2 4M6.6 6.6C3.9 8.4 2.5 12 2.5 12S6 19 12 19a9.7 9.7 0 0 0 5.4-1.6M9.9 9.9a3 3 0 0 0 4.2 4.2" />
                    </svg>
                  ) : (
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M2.5 12S6 5 12 5s9.5 7 9.5 7-3.5 7-9.5 7-9.5-7-9.5-7Z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </span>
            </label>
            {error ? (
              <div className="banner banner-error" role="alert">
                {error}
              </div>
            ) : null}
            <button
              className="action primary auth-submit"
              type="submit"
              disabled={busy}
              aria-busy={busy}
            >
              {busy ? <span className="auth-spinner" aria-hidden="true" /> : null}
              {busy ? "登录中…" : "登录"}
            </button>
          </form>
          <p className="auth-footer">QEMU / KVM 虚拟化管理平台</p>
        </div>
      </main>
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
