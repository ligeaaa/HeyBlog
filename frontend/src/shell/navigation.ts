export type NavigationItem = {
  to: string;
  label: string;
  summary: string;
};

export const publicNavigation: NavigationItem[] = [
  { to: "/stats", label: "统计总览", summary: "概览当前图谱规模、处理进度与结构变化。" },
  { to: "/blogs", label: "发现博客", summary: "统一查看系统队列、优先录入清单、URL 查库与关系线索兼容入口。" },
  { to: "/graph", label: "关系图谱", summary: "查看核心图谱、邻域展开与结构布局。" },
  { to: "/about", label: "项目介绍", summary: "了解 HeyBlog 的目标、边界与当前架构。" },
];

export const adminNavigation: NavigationItem[] = [
  { to: "/admin/control", label: "控制台", summary: "执行启动、停爬、批处理和维护操作。" },
  { to: "/admin/runtime/progress", label: "爬虫进度", summary: "跟踪 worker 状态、耗时与实时工作量。" },
  { to: "/admin/runtime/current", label: "当前处理", summary: "检查当前活跃任务、worker 与运行器快照。" },
  { to: "/admin/blog-labeling", label: "博客标注台", summary: "维护标签字典并为博客分配多标签。" },
];

export function findActiveItem(pathname: string, items: NavigationItem[]) {
  if (pathname === "/") {
    return items[0];
  }
  return items.find((item) => pathname === item.to || pathname.startsWith(`${item.to}/`)) ?? items[0];
}
