import { FormEvent, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { clearAdminToken, getAdminToken, setAdminToken } from "../lib/adminAuth";
import { findActiveItem, adminNavigation } from "./navigation";

export function AdminLayout() {
  const location = useLocation();
  const activeItem = useMemo(() => findActiveItem(location.pathname, adminNavigation), [location.pathname]);
  const [token, setToken] = useState(() => getAdminToken() ?? "");
  const [draftToken, setDraftToken] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    setAdminToken(draftToken);
    setToken(getAdminToken() ?? "");
    setDraftToken("");
  };

  const hasToken = token.trim().length > 0;

  return (
    <div className="app-shell">
      <header className="app-topbar">
        <div className="app-topbar-brand">
          <p className="eyebrow">HeyBlog</p>
          <div>
            <h1>Admin Operations</h1>
            <p className="lede">受保护的后台入口，用于 crawler 运维、标注治理和维护操作。</p>
          </div>
        </div>
        {hasToken ? (
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              clearAdminToken();
              setToken("");
            }}
          >
            退出管理访问
          </button>
        ) : null}
      </header>
      <aside className="sidebar" id="app-sidebar">
        <div className="brand-block">
          <p className="eyebrow">Admin</p>
          <h2>Operations Console</h2>
          <p className="lede">所有运行控制与治理动作都应只从这里进入，并由后端做权限校验。</p>
        </div>
        <nav className="nav-groups" aria-label="Admin navigation">
          <section className="nav-group">
            <p className="nav-group-label">Operate</p>
            <div className="nav-list">
              {adminNavigation.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                >
                  <span className="nav-link-title">{item.label}</span>
                  <span className="nav-link-copy">{item.summary}</span>
                </NavLink>
              ))}
            </div>
          </section>
        </nav>
      </aside>
      <main className="page-shell">
        <div className="page-shell-inner">
          <section className="page-context">
            <div>
              <p className="eyebrow">Admin</p>
              <p className="page-context-title">{activeItem.label}</p>
              <p className="page-context-copy">{activeItem.summary}</p>
            </div>
            <code className="page-context-path">{activeItem.to}</code>
          </section>
          {hasToken ? (
            <Outlet />
          ) : (
            <section className="surface-card">
              <div className="surface-head">
                <div>
                  <h2>管理员访问令牌</h2>
                  <p className="surface-note">输入 `HEYBLOG_ADMIN_TOKEN` 对应的 token 后才能访问后台页面。</p>
                </div>
              </div>
              <form className="search-form" onSubmit={handleSubmit}>
                <label className="search-field">
                  <span>Admin token</span>
                  <input
                    aria-label="Admin token"
                    type="password"
                    value={draftToken}
                    onChange={(event) => setDraftToken(event.target.value)}
                    placeholder="Paste admin bearer token"
                  />
                </label>
                <button className="primary-button" type="submit" disabled={!draftToken.trim()}>
                  进入后台
                </button>
              </form>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
