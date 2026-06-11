import { Loader2, LogOut, UserCircle } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Navigation } from "../components/Navigation";
import {
  confirmEmailVerification,
  fetchCurrentUser,
  fetchMyLabelStats,
  loginUser,
  logoutUser,
  registerUser,
  requestEmailVerification,
  requestPasswordReset,
  resetPassword,
} from "../lib/api";
import {
  clearStoredAuthSession,
  readStoredAuthSession,
  storeAuthSession,
  updateStoredUser,
} from "../lib/auth";
import type { AuthSession, UserProfile } from "../types/graph";

type AuthMode = "login" | "register" | "forgot" | "reset";

/**
 * Render the user auth and profile page.
 *
 * @returns Registration/login form when signed out, otherwise the current
 * user profile with a concise random-blog label total.
 */
export function ProfilePage() {
  const [searchParams] = useSearchParams();
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tokenInput, setTokenInput] = useState("");
  const [lastLifecycleToken, setLastLifecycleToken] = useState<string | null>(null);
  const [session, setSession] = useState<AuthSession | null>(() => readStoredAuthSession());
  const [user, setUser] = useState<UserProfile | null>(() => session?.user ?? null);
  const [labelCount, setLabelCount] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingProfile, setIsLoadingProfile] = useState(Boolean(session));

  useEffect(() => {
    const verifyToken = searchParams.get("verify_token")?.trim();
    const resetToken = searchParams.get("reset_token")?.trim();
    if (verifyToken) {
      void handleVerifyEmail(verifyToken);
      return;
    }
    if (resetToken) {
      setTokenInput(resetToken);
      setAuthMode("reset");
    }
  }, [searchParams]);

  useEffect(() => {
    if (!session?.token) {
      setIsLoadingProfile(false);
      return;
    }
    if (searchParams.get("verify_token")?.trim()) {
      setIsLoadingProfile(false);
      return;
    }
    void loadProfile(session.token);
  }, [searchParams, session?.token]);

  async function loadProfile(token: string) {
    try {
      setIsLoadingProfile(true);
      const [profile, labelStats] = await Promise.all([
        fetchCurrentUser(token),
        fetchMyLabelStats(token),
      ]);
      setUser(profile);
      setLabelCount(labelStats.labelCount);
      updateStoredUser(profile);
    } catch {
      clearStoredAuthSession();
      setSession(null);
      setUser(null);
      setLabelCount(0);
    } finally {
      setIsLoadingProfile(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (authMode === "forgot") {
      await handleForgotPassword();
      return;
    }
    if (authMode === "reset") {
      await handleResetPassword();
      return;
    }
    if (!email.trim() || !password) {
      toast.error("请输入邮箱和密码。");
      return;
    }
    try {
      setIsSubmitting(true);
      if (authMode === "register") {
        const payload = await registerUser({ email, password });
        setLastLifecycleToken(payload.verificationToken ?? null);
        setPassword("");
        setAuthMode("login");
        toast.success("验证邮件已发送，请验证邮箱后登录。");
        return;
      }
      const nextSession = await loginUser({ email, password });
      storeAuthSession(nextSession);
      setSession(nextSession);
      setUser(nextSession.user);
      setPassword("");
      toast.success("登录成功。");
    } catch {
      toast.error(authMode === "register" ? "注册失败，请检查邮箱、密码或待验证状态。" : "登录失败，请检查账号密码。");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleVerifyEmail(tokenOverride?: string) {
    const token = tokenOverride?.trim();
    if (!token) {
      toast.error("验证链接缺少 Token。");
      return;
    }
    try {
      setIsSubmitting(true);
      const profile = await confirmEmailVerification(token);
      if (session?.token) {
        setUser(profile);
        updateStoredUser(profile);
      } else {
        clearStoredAuthSession();
        setSession(null);
        setUser(null);
      }
      setAuthMode("login");
      setTokenInput("");
      setLastLifecycleToken(null);
      toast.success(session?.token ? "邮箱验证成功。" : "邮箱验证成功，请登录。");
    } catch {
      toast.error("邮箱验证失败，请重新发送验证邮件。");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleForgotPassword() {
    if (!email.trim()) {
      toast.error("请输入邮箱。");
      return;
    }
    try {
      setIsSubmitting(true);
      const payload = await requestPasswordReset(email);
      setLastLifecycleToken(payload.resetToken ?? null);
      setAuthMode("reset");
      toast.success("重置请求已提交。");
    } catch {
      toast.error("密码重置请求失败。");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleResetPassword() {
    const token = tokenInput.trim() || lastLifecycleToken?.trim();
    if (!token || !password) {
      toast.error("请输入重置 Token 和新密码。");
      return;
    }
    try {
      setIsSubmitting(true);
      await resetPassword({ token, password });
      clearStoredAuthSession();
      setSession(null);
      setUser(null);
      setPassword("");
      setTokenInput("");
      setLastLifecycleToken(null);
      setAuthMode("login");
      toast.success("密码已重置，请重新登录。");
    } catch {
      toast.error("密码重置失败，请检查 Token 或密码长度。");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleResendVerification() {
    const targetEmail = user?.email ?? email;
    if (!targetEmail.trim()) {
      toast.error("请输入邮箱。");
      return;
    }
    try {
      setIsSubmitting(true);
      const payload = await requestEmailVerification(targetEmail);
      toast.success(payload.alreadyVerified ? "邮箱已经验证。" : "验证邮件已发送。");
    } catch {
      toast.error("验证请求失败。");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleLogout() {
    const token = session?.token;
    clearStoredAuthSession();
    setSession(null);
    setUser(null);
    setLabelCount(0);
    if (token) {
      try {
        await logoutUser(token);
      } catch {
        // Local logout should still complete even if the session was already gone.
      }
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <Navigation />
      <main className="mx-auto max-w-5xl px-6 pb-16 pt-28 sm:px-8">
        {!user ? (
          <section className="mx-auto max-w-md rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mb-6 flex items-center gap-3">
              <UserCircle className="h-8 w-8 text-sky-600" />
              <div>
                <h1 className="text-2xl font-semibold text-slate-950">
                  {authMode === "register"
                    ? "注册账号"
                    : authMode === "forgot"
                      ? "找回密码"
                      : authMode === "reset"
                        ? "重置密码"
                    : "登录账号"}
                </h1>
                <p className="mt-1 text-sm text-slate-500">邮箱账号会用于保存你的博客标注记录。</p>
              </div>
            </div>

            <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
              {authMode !== "reset" ? (
                <label className="block text-sm font-medium text-slate-700">
                  邮箱
                  <input
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
                    autoComplete="email"
                  />
                </label>
              ) : null}
              {authMode === "reset" ? (
                <label className="block text-sm font-medium text-slate-700">
                  Token
                  <input
                    type="text"
                    value={tokenInput || lastLifecycleToken || ""}
                    onChange={(event) => setTokenInput(event.target.value)}
                    className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
                    autoComplete="one-time-code"
                  />
                </label>
              ) : null}
              {authMode !== "forgot" ? (
                <label className="block text-sm font-medium text-slate-700">
                  密码
                  <input
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
                    autoComplete={authMode === "register" || authMode === "reset" ? "new-password" : "current-password"}
                  />
                </label>
              ) : null}
              <button
                type="submit"
                disabled={isSubmitting}
                className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-slate-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
              >
                {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {authMode === "register"
                  ? "注册并发送验证邮件"
                  : authMode === "forgot"
                    ? "发送重置 Token"
                    : authMode === "reset"
                      ? "重置密码"
                      : "登录"}
              </button>
            </form>

            <button
              type="button"
              onClick={() => setAuthMode(authMode === "register" ? "login" : "register")}
              className="mt-4 w-full text-center text-sm text-sky-700 hover:text-sky-900"
            >
              {authMode === "register" ? "已有账号，去登录" : "没有账号，注册一个"}
            </button>
            <div className="mt-3 flex justify-center gap-4 text-sm">
              <button type="button" onClick={() => setAuthMode("forgot")} className="text-slate-600 hover:text-slate-950">
                忘记密码
              </button>
            </div>
          </section>
        ) : (
          <section className="space-y-6">
            <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm text-slate-500">当前账号</p>
                  <h1 className="mt-1 text-2xl font-semibold text-slate-950">{user.email}</h1>
                  <p className="mt-2 text-sm text-slate-500">显示名：{user.displayName || user.email}</p>
                  <p className="mt-1 text-sm text-slate-500">
                    身份：{user.role === "admin" ? "Admin" : "普通用户"} · 邮箱：
                    {user.emailVerified ? "已验证" : "未验证"}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {!user.emailVerified ? (
                    <button
                      type="button"
                      onClick={() => void handleResendVerification()}
                      className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm text-slate-700 transition hover:border-sky-300 hover:text-sky-700"
                    >
                      重新发送验证邮件
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => void handleLogout()}
                    className="inline-flex items-center justify-center gap-2 rounded-md border border-slate-300 bg-white px-4 py-2 text-sm text-slate-700 transition hover:border-rose-300 hover:text-rose-700"
                  >
                    <LogOut className="h-4 w-4" />
                    退出登录
                  </button>
                </div>
              </div>
              {!user.emailVerified ? (
                <div className="mt-6 border-t border-slate-100 pt-6">
                  <p className="text-sm text-slate-600">
                    验证邮件已发送，请打开邮箱并点击邮件中的验证链接。
                  </p>
                </div>
              ) : null}
            </div>

            {user.emailVerified ? (
              <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
                <h2 className="text-lg font-semibold text-slate-950">数据标注</h2>
                {isLoadingProfile ? (
                  <div className="mt-6 flex items-center gap-2 text-sm text-slate-500">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    正在加载个人数据...
                  </div>
                ) : (
                  <p className="mt-4 text-sm text-slate-500">
                    当前总共标注了 <span className="font-semibold text-slate-950">{labelCount}</span> 次。
                  </p>
                )}
              </div>
            ) : null}
          </section>
        )}
      </main>
    </div>
  );
}
