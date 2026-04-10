import { useMemo } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { findActiveItem, publicNavigation } from "./navigation";

export function PublicLayout() {
  const location = useLocation();
  const activeItem = useMemo(() => findActiveItem(location.pathname, publicNavigation), [location.pathname]);

  return (
    <div className="app-shell">
      <header className="app-topbar">
        <div className="app-topbar-brand">
          <p className="eyebrow">HeyBlog</p>
          <div>
            <h1>Blog Discovery</h1>
            <p className="lede">面向读者与博客作者的发现入口：探索图谱、查看博客、提交收录请求。</p>
          </div>
        </div>
      </header>
      <aside className="sidebar" id="app-sidebar">
        <div className="brand-block">
          <p className="eyebrow">Public</p>
          <h2>Discover Blogs</h2>
          <p className="lede">把博客发现、关系观察与自助收录整合成清晰的公共入口。</p>
        </div>
        <nav className="nav-groups" aria-label="Public navigation">
          <section className="nav-group">
            <p className="nav-group-label">Discover</p>
            <div className="nav-list">
              {publicNavigation.map((item) => (
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
              <p className="eyebrow">Public</p>
              <p className="page-context-title">{activeItem.label}</p>
              <p className="page-context-copy">{activeItem.summary}</p>
            </div>
            <code className="page-context-path">{activeItem.to}</code>
          </section>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
