# Agent Eval

`agent/` 提供一个轻量的多厂商 LLM blog 判定系统：

- 多 provider / model / API key 配置由 `agent/config.py` 解析
- 网页正文预抓取由 `data_preprocessing/` 负责
- 指标与混淆矩阵逻辑复用现有 `trainer` helper
- 输出 `summary.json`、`confusion_matrix.json`、`manifest.jsonl` 以及 FP/FN 样本导出

## 工作流程

整体流程由 `agent/eval.py` 编排，执行顺序如下：

1. 读取运行配置
   - 通过 `AgentSettings.from_env()` 读取默认 provider、默认 model、各 provider 的 API key / base URL，以及抓取并发、分类并发、RPM 限速、输出目录等参数。
   - 运行时可以用 CLI 的 `--provider` 和 `--model` 覆盖默认配置。

2. 加载数据集
   - 读取预处理后的 CSV，要求必须包含 `text` 列。
   - 为兼容超长正文，读取前会自动放宽 Python `csv` 的单字段大小限制。
   - 当前数据集按现有 trainer 语义映射 gold label：
     - `blog -> blog`
     - `others -> non_blog`
     - `company -> non_blog`

3. 构造分类输入
   - 每条样本都会构造成 `BlogJudgeInput(url, title, page_text)`。
   - `text` 列中的字面量 `\n` 会在加载时自动还原为真实换行。
   - 送给 LLM 之前会按 `--max-text-chars` 自动截断，避免超长上下文。
   - 如果 `--max-text-chars <= 0`，则不向模型传递正文，只看 `url + title`。

4. 调用 LLM 做 blog / non_blog 判定
   - `BlogClassifier` 使用 LiteLLM 调用选定 provider/model。
   - 请求按 `AGENT_CLASSIFICATION_MAX_CONCURRENCY` 控制并发。
   - 同时按 `AGENT_CLASSIFICATION_REQUESTS_PER_MINUTE` 做全局速率限制。
   - Prompt 会要求模型只返回严格 JSON：
     - `pred_label`
     - `reason`

5. 解析分类结果
   - 如果模型返回合法 JSON，且 `pred_label` 为 `blog` 或 `non_blog`，则该行记为分类成功。
   - 如果 LiteLLM 调用失败、返回内容不可解析、或标签非法，则该行记为：
     - `llm_status=failed`
     - `pred_label=null`
   - 这类样本会保留在 manifest 中，但不会进入主分类指标分母。

6. 生成逐行 manifest
   - `manifest.jsonl` 会为每条样本记录：
     - `url`
     - `title`
     - `gold_label`
     - `pred_label`
     - `fetch_status`
     - `error_kind`
     - `used_page_content`
     - `reason`
     - `final_url`
     - `provider`
     - `model`
     - `llm_status`

7. 计算 summary 与 confusion matrix
   - 主指标只基于 `pred_label != null` 的样本计算。
   - 复用：
     - `trainer.evaluation.metrics.compute_confusion_counts()`
     - `trainer.evaluation.confusion.build_confusion_matrix()`
   - `agent/eval.py` 本地计算：
     - `precision`
     - `recall`
     - `f1`
     - `accuracy`
   - 同时单独报告：
     - `page_fetch_coverage`
     - `classification_coverage`

8. 写出运行结果
   - 输出目录默认为 `data/agent/evals/<UTC timestamp>/`
   - 目录下会写出：
     - `summary.json`
     - `confusion_matrix.json`
     - `manifest.jsonl`
     - `false_positives.jsonl`
     - `false_negatives.jsonl`
     - `false_positives.csv`
     - `false_negatives.csv`

## 安装

```bash
pip install -e '.[agent]'
```

## Quick Start

下面按“最少步骤跑起来”的顺序来：

### 1. 进入项目根目录

```bash
cd /Users/lige/code/HeyBlog
```

### 2. 安装依赖

如果你还没装过项目依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[agent]'
```

如果你已经有项目 `.venv`，通常只需要：

```bash
source .venv/bin/activate
pip install -e '.[agent]'
```

### 3. 设置运行环境变量

这个 agent 会自动读取项目根目录的 `.env`，也会读取你当前 shell 里的环境变量。

推荐设置位置：

1. 临时测试
   - 直接在当前终端 `export ...`
2. 长期本地使用
   - 写到仓库根目录 `/Users/lige/code/HeyBlog/.env`

最少要配置一组 provider。当前更推荐直接走 DeepSeek 官方直连：

```bash
export AGENT_DEFAULT_PROVIDER=deepseek
export AGENT_DEFAULT_MODEL=deepseek-chat
export AGENT_PROVIDER_DEEPSEEK_MODEL=deepseek-chat
export AGENT_PROVIDER_DEEPSEEK_API_KEY=你的真实_deepseek_api_key
export AGENT_PROVIDER_DEEPSEEK_BASE_URL=https://api.deepseek.com
```

如果你想切到 reasoning 模式，可以把模型改成：

```bash
export AGENT_DEFAULT_MODEL=deepseek-reasoner
export AGENT_PROVIDER_DEEPSEEK_MODEL=deepseek-reasoner
```

### 4. 先预处理正文数据集

```bash
python -m data_preprocessing.build_agent_text_dataset \
  --csv data/blog-label-training-2026-04-11.csv \
  --output-csv data/blog-label-training-2026-04-11-with-text.csv
```

这个步骤会把网页正文抓下来并写入 `text` 列。为了便于人工检查，输出 CSV 中的 `text` 会被强制写成单行，换行会保存为字面量 `\n`。

### 5. 先跑 1 条 smoke test

可以用模块方式：

```bash
python3 -m agent.eval --csv data/blog-label-training-2026-04-11-with-text.csv --limit 1 --provider deepseek --model deepseek-chat
```

也可以用新加的 CLI 命令：

```bash
heyblog-agent-eval --csv data/blog-label-training-2026-04-11-with-text.csv --limit 1 --provider deepseek --model deepseek-chat
```

命令成功后会打印一个输出目录，里面会生成：

- `summary.json`
- `confusion_matrix.json`
- `manifest.jsonl`

如果你现在只是想确认“模型 API 能不能打通”，更推荐先跑一个更小的直连脚本，不经过抓网页和 eval：

```bash
heyblog-agent-debug-model --provider deepseek --model deepseek-chat
```

默认它会发送一句 `Reply with exactly: ok`，并打印：

- 解析后的 provider
- 解析后的 model
- 实际使用的 `api_base`
- 模型返回的原始内容
- LiteLLM 原始响应

如果你要看 LiteLLM 自己的底层调试日志：

```bash
heyblog-agent-debug-model --provider deepseek --model deepseek-chat --debug
```

如果你要自定义测试消息：

```bash
heyblog-agent-debug-model --provider deepseek --model deepseek-chat --message "Say hello in one word"
```

### 6. 再跑全量 eval

```bash
heyblog-agent-eval --csv data/blog-label-training-2026-04-11-with-text.csv --provider deepseek --model deepseek-chat
```

如果你不传 `--provider` / `--model`，系统会回落到 `AGENT_DEFAULT_PROVIDER` / `AGENT_DEFAULT_MODEL`。
如果你不传 `--csv`，默认也会读取 `data/blog-label-training-2026-04-11-with-text.csv`。
如果你想控制送给模型的正文长度，可以额外传：

```bash
heyblog-agent-eval --max-text-chars 8000
```

如果你只想看 `url + title`，可以传：

```bash
heyblog-agent-eval --max-text-chars 0
```

## 环境变量

至少需要：

```bash
export AGENT_DEFAULT_PROVIDER=deepseek
export AGENT_DEFAULT_MODEL=deepseek-chat
export AGENT_PROVIDER_DEEPSEEK_MODEL=deepseek-chat
export AGENT_PROVIDER_DEEPSEEK_API_KEY=...
export AGENT_PROVIDER_DEEPSEEK_BASE_URL=https://api.deepseek.com
```

可选：

```bash
export AGENT_PROVIDER_DEEPSEEK_MODEL=deepseek-reasoner
export AGENT_FETCH_MAX_CONCURRENCY=4
export AGENT_CLASSIFICATION_MAX_CONCURRENCY=2
export AGENT_CLASSIFICATION_REQUESTS_PER_MINUTE=60
export AGENT_FETCH_TIMEOUT_SECONDS=10
export AGENT_MAX_PAGE_BYTES=2000000
export AGENT_OUTPUT_ROOT=/Users/lige/code/HeyBlog/data/agent/evals
```

常见变量说明：

- `AGENT_DEFAULT_PROVIDER`
  - 默认 provider 名称，例如 `deepseek`
- `AGENT_DEFAULT_MODEL`
  - 默认 model 名称；CLI 不传 `--model` 时使用
- `AGENT_PROVIDER_<NAME>_MODEL`
  - 某个 provider 的默认模型
- `AGENT_PROVIDER_<NAME>_API_KEY`
  - 某个 provider 的 API key
- `AGENT_PROVIDER_<NAME>_BASE_URL`
  - 官方 DeepSeek 直连时建议设置为 `https://api.deepseek.com`
- `AGENT_FETCH_MAX_CONCURRENCY`
  - 页面抓取并发
- `AGENT_CLASSIFICATION_MAX_CONCURRENCY`
  - LLM 请求并发
- `AGENT_CLASSIFICATION_REQUESTS_PER_MINUTE`
  - 每分钟请求上限
- `AGENT_FETCH_TIMEOUT_SECONDS`
  - 页面抓取超时时间
- `AGENT_MAX_PAGE_BYTES`
  - 单页最大抓取字节数
- `AGENT_OUTPUT_ROOT`
  - eval 结果默认输出目录

## 在哪设置这些变量

推荐优先级如下：

1. 项目根目录 `.env`
   - 路径：`/Users/lige/code/HeyBlog/.env`
   - 适合长期本地开发
   - `AgentSettings.from_env()` 会自动读取这里
2. 当前 shell 会话
   - 适合临时切换 provider / model / API key
   - shell 里的值会覆盖 `.env`
3. 不建议写死在代码里
   - API key、base URL、provider 选择都不应该直接写进 `agent/*.py`

一个推荐的 `.env` 示例：

```bash
AGENT_DEFAULT_PROVIDER=deepseek
AGENT_DEFAULT_MODEL=deepseek-chat

AGENT_PROVIDER_DEEPSEEK_MODEL=deepseek-chat
AGENT_PROVIDER_DEEPSEEK_API_KEY=你的真实_deepseek_key
AGENT_PROVIDER_DEEPSEEK_BASE_URL=https://api.deepseek.com

# 如果你想切到 reasoning 模式：
# AGENT_PROVIDER_DEEPSEEK_MODEL=deepseek-reasoner

AGENT_FETCH_MAX_CONCURRENCY=4
AGENT_CLASSIFICATION_MAX_CONCURRENCY=2
AGENT_CLASSIFICATION_REQUESTS_PER_MINUTE=60
AGENT_FETCH_TIMEOUT_SECONDS=10
AGENT_MAX_PAGE_BYTES=2000000
```

## 运行

单条 smoke test：

```bash
heyblog-agent-eval --csv data/blog-label-training-2026-04-11.csv --limit 1 --provider deepseek --model deepseek-chat
```

全量 eval：

```bash
heyblog-agent-eval --csv data/blog-label-training-2026-04-11.csv --provider deepseek --model deepseek-chat
```

## 指标

`summary.json` 输出：

- `tp`
- `tn`
- `fp`
- `fn`
- `precision`
- `recall`
- `f1`
- `accuracy`
- `page_fetch_coverage`
- `classification_coverage`

`manifest.jsonl` 为逐行可审计结果：

- `fetch_status=failed` 表示页面抓取失败
- `used_page_content=false` 表示回退到仅 `url + title`
- `llm_status=failed` 且 `pred_label=null` 表示该行未进入主指标分母
