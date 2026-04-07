import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

type NavigationItem = {
  to: string;
  label: string;
  summary: string;
};

type NavigationGroup = {
  title: string;
  eyebrow: string;
  items: NavigationItem[];
};

const navigationGroups: NavigationGroup[] = [
  {
    title: "Discover",
    eyebrow: "Explore",
    items: [
      { to: "/stats", label: "统计总览", summary: "概览当前图谱规模、处理进度与结构变化。" },
      { to: "/blogs", label: "发现博客", summary: "筛选、翻页并快速进入已抓取博客详情。" },
      { to: "/search", label: "搜索发现", summary: "通过查询词与关系线索继续扩展发现范围。" },
      { to: "/graph", label: "关系图谱", summary: "查看核心图谱、邻域展开与结构布局。" },
      { to: "/about", label: "项目介绍", summary: "了解 HeyBlog 的目标、边界与当前架构。" },
    ],
  },
  {
    title: "Operations",
    eyebrow: "Operate",
    items: [
      { to: "/blog-labeling", label: "博客标注台", summary: "维护标签字典并为博客分配多标签。" },
      { to: "/runtime/progress", label: "爬虫进度", summary: "跟踪 worker 状态、耗时与实时工作量。" },
      { to: "/runtime/current", label: "当前处理", summary: "检查当前活跃任务、worker 与运行器快照。" },
      { to: "/control", label: "控制台", summary: "执行启动、停爬、批处理和维护操作。" },
    ],
  },
];

const navigationItems = navigationGroups.flatMap((group) =>
  group.items.map((item) => ({ ...item, groupTitle: group.title, groupEyebrow: group.eyebrow })),
);

function findActiveItem(pathname: string) {
  if (pathname === "/") {
    return navigationItems.find((item) => item.to === "/stats") ?? navigationItems[0];
  }

  return (
    navigationItems.find((item) => pathname === item.to || pathname.startsWith(`${item.to}/`)) ??
    navigationItems[0]
  );
}

export function AppLayout() {
  const location = useLocation();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const activeItem = useMemo(() => findActiveItem(location.pathname), [location.pathname]);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  return (
    <div className="app-shell">
      <header className="app-topbar">
        <div className="app-topbar-brand">
          <p className="eyebrow">HeyBlog</p>
          <div>
            <h1>Repository Control Surface</h1>
            <p className="lede">参考 GitHub 的层级与密度，保留发现、运行时与维护能力。</p>
          </div>
        </div>
        <div className="app-topbar-meta">
          <div className="topbar-pill">
            <span>Active</span>
            <strong>{activeItem.label}</strong>
          </div>
          <button
            type="button"
            className="secondary-button nav-toggle"
            aria-expanded={mobileNavOpen}
            aria-controls="app-sidebar"
            onClick={() => {
              setMobileNavOpen((current) => !current);
            }}
          >
            {mobileNavOpen ? "收起导航" : "展开导航"}
          </button>
        </div>
      </header>
      <aside className={`sidebar${mobileNavOpen ? " open" : ""}`} id="app-sidebar">
        <div className="brand-block">
          <p className="eyebrow">Command Center</p>
          <h2>Blog Discovery Entry</h2>
          <p className="lede">把博客发现、关系观察、人工标注与爬虫运维收敛到统一的应用壳层里。</p>
        </div>
        <nav className="nav-groups" aria-label="Primary">
          {navigationGroups.map((group) => (
            <section key={group.title} className="nav-group">
              <p className="nav-group-label">{group.title}</p>
              <div className="nav-list">
                {group.items.map((item) => (
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
          ))}
        </nav>
      </aside>
      <main className="page-shell">
        <div className="page-shell-inner">
          <section className="page-context">
            <div>
              <p className="eyebrow">{activeItem.groupEyebrow}</p>
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
