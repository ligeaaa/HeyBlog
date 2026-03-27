import { NavLink, Outlet } from "react-router-dom";

const navigation = [
  { to: "/stats", label: "统计总览" },
  { to: "/blogs", label: "Blog 概览" },
  { to: "/runtime/current", label: "当前处理" },
  { to: "/control", label: "控制台" },
  { to: "/about", label: "项目介绍" },
];

export function AppLayout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <p className="eyebrow">HeyBlog Console</p>
          <h1>Blog Graph Operations</h1>
          <p className="lede">现代化操作台，解耦 Python 模板，按页面组织运行态、概览与控制能力。</p>
        </div>
        <nav className="nav-list">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="page-shell">
        <Outlet />
      </main>
    </div>
  );
}
