import { useState } from "react";

import { api } from "../api";
import type { CurrentUser } from "../types";
import { describeError } from "../components/ui";

function AuthBackdrop() {
  return (
    <div className="auth-bg" aria-hidden="true">
      <div className="auth-bg-grid" />
      <div className="auth-bg-orb auth-bg-orb-a" />
      <div className="auth-bg-orb auth-bg-orb-b" />
      <div className="auth-bg-orb auth-bg-orb-c" />
      <svg
        className="auth-bg-net"
        viewBox="0 0 1440 900"
        preserveAspectRatio="xMidYMid slice"
      >
        <g className="auth-bg-links">
          <path d="M80 160 L260 90 L420 210 L300 330 L80 160Z" />
          <path d="M260 90 L520 60 L420 210" />
          <path d="M300 330 L180 520 L60 640" />
          <path d="M180 520 L360 690 L240 840" />
          <path d="M1060 110 L1220 60 L1380 170 L1250 300 L1060 110Z" />
          <path d="M1250 300 L1400 420 L1300 560" />
          <path d="M1300 560 L1120 690 L1200 840 L1390 780 L1300 560" />
          <path d="M1120 690 L980 820" />
        </g>
        <g className="auth-bg-nodes">
          <circle cx="80" cy="160" r="3" />
          <circle cx="260" cy="90" r="4" />
          <circle cx="420" cy="210" r="3" />
          <circle cx="300" cy="330" r="4.5" />
          <circle cx="520" cy="60" r="2.5" />
          <circle cx="180" cy="520" r="3.5" />
          <circle cx="60" cy="640" r="2.5" />
          <circle cx="360" cy="690" r="3" />
          <circle cx="240" cy="840" r="2.5" />
          <circle cx="1060" cy="110" r="3" />
          <circle cx="1220" cy="60" r="2.5" />
          <circle cx="1380" cy="170" r="3.5" />
          <circle cx="1250" cy="300" r="4.5" />
          <circle cx="1400" cy="420" r="2.5" />
          <circle cx="1300" cy="560" r="4" />
          <circle cx="1120" cy="690" r="3.5" />
          <circle cx="1200" cy="840" r="2.5" />
          <circle cx="1390" cy="780" r="3" />
          <circle cx="980" cy="820" r="2.5" />
        </g>
      </svg>
      <div className="auth-bg-vignette" />
    </div>
  );
}

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
      <AuthBackdrop />
      <main className="auth-main">
        <div className="auth-card">
          <div className="auth-card-brand">
            <BrandMark />
            <span className="auth-brand-name">CloudVirt</span>
          </div>
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
        </div>
        <p className="auth-copyright">
          © {new Date().getFullYear()} CloudVirt · QEMU / KVM 虚拟化管理平台
        </p>
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
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError("两次输入的新密码不一致");
      return;
    }
    setBusy(true);
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
              autoComplete="current-password"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              required
            />
          </label>
          <label>
            新密码（至少 12 位）
            <input
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              minLength={12}
              required
            />
          </label>
          <label>
            确认新密码
            <input
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              minLength={12}
              required
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
