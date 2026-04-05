import { NavLink, Outlet } from "react-router-dom";

const navigation = [
  { to: "/stats", label: "统计总览" },
  { to: "/blogs", label: "发现博客" },
  { to: "/search", label: "搜索发现" },
  { to: "/graph", label: "关系图谱" },
  { to: "/runtime/progress", label: "爬虫进度" },
  { to: "/runtime/current", label: "当前处理" },
  { to: "/control", label: "控制台" },
  { to: "/about", label: "项目介绍" },
];

export function AppLayout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <p className="eyebrow">HeyBlog</p>
          <h1>Blog Discovery Entry</h1>
          <p className="lede">先把博客变得更容易被看见、被理解、被继续探索；操作能力仍在，但不再是首页叙事中心。</p>
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
