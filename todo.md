# HeyBlog Todo

## Maintenance Rules

- Keep active work concrete and user-facing.
- Link each substantial item to its tracker document.
- Update this file and the corresponding tracker together when status changes.

## Active

None.

## Completed

- [x] 修复 admin 标注候选慢查询导致 stats/status 连锁 timeout。Tracker: `tracker/admin-labeling-timeout-hotfix-20260525.md` (created 2026-05-25 22:44:07 BST; completed 2026-05-25).
- [x] 收敛数据标注台候选、持久化 title 与导出接口契约。Tracker: `tracker/labeling-workbench-title-export-cleanup-20260525.md` (created 2026-05-25 22:08:37 BST; completed 2026-05-25).
- [x] 新增 URL-keyed 旧版 label CSV 导入脚本，可清空 `blog_labels` 后按计数字典导入。Tracker: `tracker/legacy-label-count-import-20260525.md` (created 2026-05-25 21:21:44 BST; completed 2026-05-25).
- [x] 将人工 label 收敛为单表 URL-keyed 计数字典，并同步 API、迁移、测试、文档。Tracker: `tracker/single-table-label-counts-20260525.md` (created 2026-05-25 20:50:31 BST; completed 2026-05-25).
- [x] 将人工 label 改为按 normalized URL 长期持久化，并确保数据库 reset 不删除 label/tag/parquet 相关数据。Tracker: `tracker/url-keyed-label-persistence-20260525.md` (created 2026-05-25 15:46:48 BST; completed 2026-05-25).
- [x] 将 backend 调 persistence-api 的 URL refilter execute 请求 timeout 单独延长到 7 天，避免长任务被默认 10 秒 HTTP timeout 标记失败。Tracker: `tracker/url-refilter-execute-timeout-20260525.md` (created 2026-05-25 14:27:13 BST; completed 2026-05-25).
- [x] URL refilter 激活 success 时，source blog 缺失仍创建 target blog 但跳过 edge 创建，避免 `edges.from_blog_id` 外键失败。Tracker: `tracker/url-refilter-missing-source-edge-20260525.md` (created 2026-05-25 14:18:00 BST; completed 2026-05-25).
- [x] 让 URL refilter 删除 blog/edge 前显式检查目标是否仍存在，避免重复进度或并发清理导致删除路径报错。Tracker: `tracker/url-refilter-idempotent-delete-20260525.md` (created 2026-05-25 14:05:05 BST; completed 2026-05-25).
- [x] 迁移 `blog_label_assignments.blog_id` 从旧 blog id 到 raw id 的一次性脚本。Tracker: `tracker/blog-label-assignment-id-migration-20260524.md` (created 2026-05-24 21:40:20 BST; completed 2026-05-24).
- [x] 在 raw URL 过滤链前新增重复 URL 过滤，并调整标注保存 ID 解析优先级。Tracker: `tracker/raw-url-dedup-label-id-20260524.md` (created 2026-05-24 21:00:11 BST; completed 2026-05-24).
- [x] 调整 raw-derived blog_id 语义，并核对 Admin raw URL 重过滤入口。Tracker: `tracker/raw-blog-id-refilter-admin-20260524.md` (created 2026-05-24 20:53:02 BST; completed 2026-05-24).
- [x] 扩展数据标注台候选范围到模型过滤前已处理 raw URL，并同步旧 label 导入脚本。Tracker: `tracker/raw-url-labeling-scope-20260524.md` (created 2026-05-24 20:32:46 BST; completed 2026-05-24).
- [x] 新增旧版博客 label CSV 临时导入脚本。Tracker: `tracker/legacy-label-import-script-20260524.md` (created 2026-05-24 20:14:18 BST; completed 2026-05-24).
- [x] 完善管理员数据标注台：label 实时统计、parquet 保存/补齐/重建/下载。Tracker: `tracker/admin-labeling-parquet-export-20260524.md` (created 2026-05-24 19:50:18 BST; completed 2026-05-24).
- [x] 修复 URL refilter 过程中重复插入 `edges` 导致的 `uq_edges_from_to` 唯一键冲突。Tracker: `tracker/raw-blog-id-refilter-admin-20260524.md` (created 2026-05-24 20:53:02 BST; completed 2026-05-24).
- [x] 移除 `raw_discovered_urls.source_blog_id` 到 `blogs.blog_id` 的强外键，并确保 Postgres 启动执行兼容迁移，避免 raw 原始记录随派生 blog 删除。Tracker: `tracker/raw-blog-id-refilter-admin-20260524.md` (created 2026-05-24 20:53:02 BST; completed 2026-05-24; startup sync fix 2026-05-25).
- [x] 将高风险 URL refilter 操作写入独立 `url-refilter` 日志目录，与 backend/crawler/persistence-api 并列，并补齐开始、结束/退出/关闭原因与每 10k 进度日志。Tracker: `tracker/log-system.md` (created 2026-05-24; completed 2026-05-25).
- [x] Established the unified logging system across all Python services, including shared module, type-grouped hourly log slices, one-week retention cleanup, request-id propagation, Docker log volume, docs, env templates, and tests. Tracker: `tracker/log-system.md` (created 2026-05-24; completed 2026-05-24).
