import { Navigation } from "../components/Navigation";
import avatarImage from "../assets/images/avatar.png";

/**
 * Render the project background, contact details, and mascot artwork.
 *
 * @returns About page UI.
 */
export function AboutPage() {
  return (
    <div className="h-screen overflow-hidden bg-slate-50">
      <Navigation />

      <main className="mx-auto flex h-full max-w-6xl items-center px-5 pb-5 pt-20 sm:px-8 sm:pt-24">
        <section className="grid h-full max-h-[760px] w-full grid-rows-[minmax(0,1fr)_minmax(180px,0.58fr)] items-stretch gap-3 sm:gap-5 lg:grid-cols-[1.04fr_0.96fr] lg:grid-rows-1">
          <div className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-3 sm:flex sm:flex-col sm:gap-5">
            <div className="rounded-[24px] border border-slate-200 bg-white/88 p-4 shadow-[0_18px_42px_rgba(15,23,42,0.08)] sm:rounded-[28px] sm:p-7">
              <h1 className="text-4xl font-bold tracking-normal text-slate-950 sm:text-6xl lg:text-7xl">HeyBlog</h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600 sm:mt-5 sm:text-lg sm:leading-8 lg:text-xl lg:leading-9">
                每个人细究起来都蛮有意思，只是人很少有被人仔细看见的机会，以至于被仔细看见这件事有点近似于爱。
              </p>
            </div>

            <div className="grid min-h-0 gap-3 sm:flex-1 sm:grid-cols-2 sm:gap-4">
              <article className="min-h-0 overflow-hidden rounded-2xl border border-slate-200 bg-white/86 p-4 shadow-[0_14px_30px_rgba(15,23,42,0.06)] sm:p-5">
                <h2 className="text-base font-semibold tracking-normal text-slate-950 sm:text-xl">项目背景</h2>
                <p className="mt-2 text-xs leading-5 text-slate-600 sm:mt-3 sm:text-base sm:leading-8">
                  很久以前，就对探索网络社区的社交关系非常感兴趣。于是某天晚上灵光一现：如果从一个随机个人博客出发，自动爬取其友链，根据友链找到新的博客，不断延伸，理论上可以找到网络上所有的个人博客。
                </p>
              </article>

              <article className="min-h-0 overflow-hidden rounded-2xl border border-slate-200 bg-white/86 p-4 shadow-[0_14px_30px_rgba(15,23,42,0.06)] sm:p-5">
                <h2 className="text-base font-semibold tracking-normal text-slate-950 sm:text-xl">当前状态</h2>
                <p className="mt-2 text-xs leading-5 text-slate-600 sm:mt-3 sm:text-base sm:leading-8">
                  构建博客爬取 Benchmark 中，思考有哪些特征可以提取，思考如何构架一个博客二分类模型，思考 agent 在该项目的可行性，思考该项目的意义。
                </p>
              </article>
            </div>

            <section className="rounded-2xl border border-slate-200 bg-white/86 p-4 shadow-[0_14px_30px_rgba(15,23,42,0.06)] sm:p-5">
              <h2 className="text-base font-semibold tracking-normal text-slate-950 sm:text-xl">联系方式</h2>
              <div className="mt-2 grid gap-1 text-xs leading-5 text-slate-600 sm:mt-3 sm:grid-cols-2 sm:gap-3 sm:text-base sm:leading-7">
                <p>
                  Github：
                  <a
                    href="https://github.com/ligeaaa/HeyBlog"
                    target="_blank"
                    rel="noreferrer"
                    className="font-medium text-sky-600 transition-colors hover:text-sky-700"
                  >
                    ligeaaa/HeyBlog
                  </a>
                </p>
                <p>Q群：如果你对该项目感兴趣，欢迎加Q群：399523190</p>
              </div>
            </section>
          </div>

          <div className="relative mx-auto flex min-h-0 w-full max-w-[280px] items-stretch sm:max-w-md lg:max-w-none">
            <div className="absolute inset-x-10 bottom-8 h-24 rounded-full bg-slate-200/45 blur-3xl" />
            <div className="relative flex w-full items-end justify-center overflow-hidden rounded-[32px] border border-slate-200 bg-white shadow-[0_24px_60px_rgba(15,23,42,0.12)]">
              <img
                src={avatarImage}
                alt="HeyBlog avatar"
                className="h-full w-full object-cover object-center drop-shadow-[0_22px_28px_rgba(15,23,42,0.18)]"
              />
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
