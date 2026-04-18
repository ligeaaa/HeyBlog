# HeyBlog

基于友链智能发现网络上所有的博客！

在线访问：http://heyblog.magic-knowledge.top/

如果你对该项目感兴趣，欢迎加Q群：399523190

！！前排提醒！！

- AI率99%
- 所有文档都由AI生成，仅供参考
- 有空有精力的时候会自己检查代码和文档的
- 有任何问题欢迎提 issue 或 PR

---------


## 文档导航

- [项目结构](doc/project-structure.md)：目录、源码归属和主要入口
- [服务总览](doc/services-overview.md)：服务职责、依赖关系和修改边界
- [服务架构](doc/service-architecture.md)：运行时调用链和数据归属
- [API 文档](doc/api-docs.md)：公共、管理和内部 HTTP 协议
- [配置参考](doc/config-reference.md)：环境变量、默认值和消费者
- [开发工作流](doc/developer-workflows.md)：常见任务从哪里开始
- [公开面与管理面边界](doc/public-admin-boundary.md)：拆分后的路由、API 和鉴权矩阵
- [爬虫与 URL 过滤逻辑](doc/crawler-url-filtering.md)：crawler 执行链路、URL 过滤和模型共识

## Quick Start

### 1. 仅 API / 后端最小路径

当你只想调试 HTTP 协议、聚合层行为，或者暂时不需要浏览器界面时，走这条路径最合适。
不过 `backend` 仍然依赖三个内部服务，所以最小可用本地栈依然是：

- `persistence-api`
- `crawler`
- `search`
- `backend`

先创建虚拟环境并安装依赖：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

首次运行时先准备本地配置：

```bash
cp .env.example .env
```

然后在不同终端中分别启动服务：

```bash
python -m uvicorn persistence_api.main:app --reload --port 8030
```

```bash
python -m uvicorn crawler.main:app --reload --port 8010
```

```bash
python -m uvicorn search.main:app --reload --port 8020
```

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

最后可以这样确认公共 API 已经联通：

```bash
curl http://127.0.0.1:8000/api/status
```

### 2. Docker 拆分运行时

如果你想直接跑完整本地拓扑，包括浏览器界面和 PostgreSQL 持久化后端，推荐使用 Docker：

```bash
docker compose up --build
```

如果你手动设置了 `HEYBLOG_DB_DSN`，请使用 SQLAlchemy 的 psycopg v3 DSN 形式：

`postgresql+psycopg://...`

默认服务与端口如下：

- `frontend`：`http://127.0.0.1:3000`
- `backend`：`http://127.0.0.1:8000`
- `crawler`：`http://127.0.0.1:8010`
- `search`：`http://127.0.0.1:8020`
- `persistence-api`：`http://127.0.0.1:8030`
- `persistence-db`：`127.0.0.1:5432`

Docker 会把运行时数据持久化到这些目录：

- `volumes/postgres`
- `volumes/exports`
- `volumes/search-cache`

### 3. 前端开发路径

如果你正在修改 `frontend/src/`，并希望联调公开/管理界面以及后面的真实后端 API，可以走这条路径。

先安装前端依赖：

```bash
cd frontend
npm install
```

构建前端产物：

```bash
cd frontend
npm run build
```

再用本地 backend 启动构建后的前端服务：

```bash
python -m uvicorn frontend.server:app --reload --port 3000
```

当前需要注意：

- `frontend/src/lib/api.ts` 走的是同源 `/api/*`
- `frontend/vite.config.ts` 目前没有内置 dev proxy

所以如果你直接运行：

```bash
cd frontend && npm run dev
```

你需要自己准备 `/api` 反向代理，或者使用 mock API。

### 4. 离线训练基线路径

如果你想运行当前基于 `url + title` 的离线博客分类 baseline，可以用导出的标注 CSV 启动训练：

```bash
python -m trainer.cli full-run --source-csv data/blog-label-training-2026-04-11.csv
```

训练输出会落在：

- `data/trainer/datasets/`
- `data/model/`

需要注意，运行时服务不会直接读取 `data/model/` 下的训练输出。

真正供运行时加载的模型应当被发布到：

- `runtime_resources/models/url_decision/current/`

然后通过把 `HEYBLOG_DECISION_MODEL_ROOT` 指向这个运行时资源目录，让本地调试、测试和 Docker 运行时保持一致。



