import { Loader2, LogOut, UserCircle } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { toast } from "sonner";
import { Navigation } from "../components/Navigation";
import {
  fetchCurrentUser,
  fetchMyLabelStats,
  loginUser,
  logoutUser,
  registerUser,
} from "../lib/api";
import {
  clearStoredAuthSession,
  readStoredAuthSession,
  storeAuthSession,
  updateStoredUser,
} from "../lib/auth";
import type { AuthSession, UserProfile } from "../types/graph";

type AuthMode = "login" | "register";

/**
 * Render the user auth and profile page.
 *
 * @returns Registration/login form when signed out, otherwise the current
 * user profile with a concise random-blog label total.
 */
export function ProfilePage() {
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [session, setSession] = useState<AuthSession | null>(() => readStoredAuthSession());
  const [user, setUser] = useState<UserProfile | null>(() => session?.user ?? null);
  const [labelCount, setLabelCount] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingProfile, setIsLoadingProfile] = useState(Boolean(session));

  useEffect(() => {
    if (!session?.token) {
      setIsLoadingProfile(false);
      return;
    }
    void loadProfile(session.token);
  }, [session?.token]);

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
    if (!email.trim() || !password) {
      toast.error("请输入邮箱和密码。");
      return;
    }
    try {
      setIsSubmitting(true);
      const nextSession =
        authMode === "register"
          ? await registerUser({ email, password })
          : await loginUser({ email, password });
      storeAuthSession(nextSession);
      setSession(nextSession);
      setUser(nextSession.user);
      setPassword("");
      toast.success(authMode === "register" ? "注册成功，已登录。" : "登录成功。");
    } catch {
      toast.error(authMode === "register" ? "注册失败，请检查邮箱或密码。" : "登录失败，请检查账号密码。");
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
                  {authMode === "register" ? "注册账号" : "登录账号"}
                </h1>
                <p className="mt-1 text-sm text-slate-500">邮箱和密码会用于保存你的博客标注记录。</p>
              </div>
            </div>

            <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
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
              <label className="block text-sm font-medium text-slate-700">
                密码
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
                  autoComplete={authMode === "register" ? "new-password" : "current-password"}
                />
              </label>
              <button
                type="submit"
                disabled={isSubmitting}
                className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-slate-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
              >
                {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {authMode === "register" ? "注册并登录" : "登录"}
              </button>
            </form>

            <button
              type="button"
              onClick={() => setAuthMode(authMode === "register" ? "login" : "register")}
              className="mt-4 w-full text-center text-sm text-sky-700 hover:text-sky-900"
            >
              {authMode === "register" ? "已有账号，去登录" : "没有账号，注册一个"}
            </button>
          </section>
        ) : (
          <section className="space-y-6">
            <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm text-slate-500">当前账号</p>
                  <h1 className="mt-1 text-2xl font-semibold text-slate-950">{user.email}</h1>
                  <p className="mt-2 text-sm text-slate-500">显示名：{user.displayName || user.email}</p>
                </div>
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
          </section>
        )}
      </main>
    </div>
  );
}
