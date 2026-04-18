import { Database, Globe, Network, Search, ShieldCheck, Sparkles } from "lucide-react";
import { Navigation } from "../components/Navigation";

const features = [
  {
    icon: Globe,
    title: "站点发现",
    description: "crawler 会从 seed 和友情链接页面持续发现新的博客入口，并更新图谱节点池。",
    accent: "bg-sky-100 text-sky-700 border-sky-200",
  },
  {
    icon: Database,
    title: "持久化建模",
    description: "persistence 服务维护博客、边、录入请求与 graph snapshot，保证 API 输出稳定一致。",
    accent: "bg-emerald-100 text-emerald-700 border-emerald-200",
  },
  {
    icon: Network,
    title: "关系图谱",
    description: "前端使用 AntV G6 呈现博客之间的连接关系，支持全图浏览和局部邻域探索。",
    accent: "bg-violet-100 text-violet-700 border-violet-200",
  },
  {
    icon: Search,
    title: "统一检索",
    description: "首页与图谱页共享 URL lookup 和录入流程，便于快速判断博客是否已经被系统收录。",
    accent: "bg-amber-100 text-amber-700 border-amber-200",
  },
  {
    icon: ShieldCheck,
    title: "管理员控制面",
    description: "admin 页面映射 runtime、crawl、数据库维护与 dedup 任务，直接对齐现有 backend 管理接口。",
    accent: "bg-rose-100 text-rose-700 border-rose-200",
  },
  {
    icon: Sparkles,
    title: "演示风格对齐",
    description: "当前界面结构和视觉语言参考 `frontend_example`，同时保留 HeyBlog 真实数据与业务流程。",
    accent: "bg-indigo-100 text-indigo-700 border-indigo-200",
  },
];

/**
 * Render the about route describing the current project surface.
 *
 * @returns About page UI.
 */
export function AboutPage() {
  return (
    <div className="min-h-screen overflow-x-hidden bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.18),_transparent_32%),linear-gradient(180deg,_#eef6ff_0%,_#ffffff_48%,_#f6fbff_100%)]">
      <Navigation />

      <main className="mx-auto max-w-6xl px-6 pb-16 pt-24 sm:px-8">
        <section className="mb-14 rounded-[36px] border border-slate-200 bg-white/90 px-8 py-10 shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
          <div className="inline-flex rounded-full bg-sky-100 px-4 py-2 text-sm text-sky-700">About HeyBlog</div>
          <h1 className="mt-5 text-5xl text-slate-950">一个把博客发现、图谱关系和运维面连接在一起的前端入口。</h1>
          <p className="mt-6 max-w-4xl text-lg leading-8 text-slate-600">
            当前正式 `frontend` 已不再只是一个图谱壳子。我们把首页、可视化、about、admin 四个入口统一进一个导航结构中，
            让公开浏览、关系探索和管理操作都能在同一套视觉语言下完成。
          </p>
        </section>

        <section className="mb-14 grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
          {features.map((feature) => {
            const Icon = feature.icon;
            return (
              <article
                key={feature.title}
                className="rounded-[28px] border border-slate-200 bg-white/95 p-6 shadow-[0_18px_40px_rgba(15,23,42,0.08)]"
              >
                <div className={`mb-4 inline-flex rounded-2xl border p-3 ${feature.accent}`}>
                  <Icon className="h-6 w-6" />
                </div>
                <h2 className="text-2xl text-slate-950">{feature.title}</h2>
                <p className="mt-3 text-sm leading-7 text-slate-600">{feature.description}</p>
              </article>
            );
          })}
        </section>

        <section className="rounded-[36px] bg-slate-900 px-8 py-10 text-white shadow-[0_30px_80px_rgba(15,23,42,0.24)]">
          <h2 className="text-3xl">当前页面结构</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
              <h3 className="text-xl">首页</h3>
              <p className="mt-2 text-sm leading-7 text-slate-200">
                展示当前统计、抓取队列状态、URL 搜索入口和卡片式博客目录，是 public discovery 的默认落点。
              </p>
            </div>
            <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
              <h3 className="text-xl">可视化</h3>
              <p className="mt-2 text-sm leading-7 text-slate-200">
                保留真实图谱、局部子图、节点详情、录入请求与多候选 disambiguation 流程。
              </p>
            </div>
            <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
              <h3 className="text-xl">About</h3>
              <p className="mt-2 text-sm leading-7 text-slate-200">
                提供项目背景、服务职责和当前前端重构后的使用方式。
              </p>
            </div>
            <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
              <h3 className="text-xl">Admin</h3>
              <p className="mt-2 text-sm leading-7 text-slate-200">
                引导管理员输入 token 后调用真实 `/api/admin/*`，查看 runtime、dedup 与维护操作反馈。
              </p>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
