import { Navigation } from "../components/Navigation";

/**
 * Render the simplified about route with one project background card.
 *
 * @returns About page UI.
 */
export function AboutPage() {
  return (
    <div className="min-h-screen overflow-x-hidden bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.18),_transparent_32%),linear-gradient(180deg,_#eef6ff_0%,_#ffffff_48%,_#f6fbff_100%)]">
      <Navigation />

      <main className="mx-auto max-w-4xl px-6 pb-16 pt-24 sm:px-8">
        <section className="rounded-[36px] border border-slate-200 bg-white/92 p-8 shadow-[0_18px_40px_rgba(15,23,42,0.08)] sm:p-10">
          <div className="space-y-8 text-slate-700">
            <div>
              <h1 className="text-2xl text-slate-950">项目背景</h1>
              <p className="mt-4 text-base leading-8">
                很久以前，就对探索网络社区的社交关系非常感兴趣，于是某天晚上灵光一现，如果从一个随机个人博客出发，自动爬取其友链，根据友链找到新的博客，不断延伸，理论上我可以找到网络上所有的个人博客（以连通图为前提）！
              </p>
            </div>

            <div>
              <h2 className="text-2xl text-slate-950">随口吐槽</h2>
              <p className="mt-4 text-base leading-8">
                这个项目的前端好重要——目前完全无法展示我觉得最有趣的“博客连接图”的部分qwq，仍在努力中，也期待有佬能够提供帮助。。
              </p>
            </div>

            <div>
              <h2 className="text-2xl text-slate-950">联系方式</h2>
              <div className="mt-4 space-y-3 text-base leading-8">
                <div>
                  Github:
                  {" "}
                  <a
                    href="https://github.com/ligeaaa/HeyBlog"
                    target="_blank"
                    rel="noreferrer"
                    className="text-sky-600 transition-colors hover:text-sky-700"
                  >
                    https://github.com/ligeaaa/HeyBlog
                  </a>
                </div>
                <p>Q群：如果你对该项目感兴趣，欢迎加Q群：399523190</p>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
