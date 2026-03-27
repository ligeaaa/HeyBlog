import { PageHeader } from "../components/PageHeader";
import { Surface } from "../components/Surface";

export function AboutPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Project"
        title="项目介绍"
        description="HeyBlog 用于抓取 blogroll / 友链关系，并构建博客图谱。"
      />
      <Surface title="项目做什么">
        <p>
          系统从 seed blog 列表开始，发现友情链接页，提取外链博客，记录 blogs、edges 和 crawl
          logs，再通过 split runtime 提供前端、后端、爬虫、搜索与持久化服务。
        </p>
      </Surface>
      <Surface title="当前架构">
        <ul className="plain-list">
          <li>前端：React + TypeScript + Vite</li>
          <li>后端：FastAPI API 聚合层</li>
          <li>爬虫：独立 crawler 服务与运行器状态机</li>
          <li>搜索：轻量可重建索引服务</li>
          <li>持久化：persistence-api + persistence-db(Postgres)</li>
        </ul>
      </Surface>
    </div>
  );
}
