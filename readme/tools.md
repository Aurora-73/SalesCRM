# Agent 工具集

## 概述

`engine/tools.py` 是 Agent 的统一数据入口。所有数据操作必须通过这里的函数，禁止直接查数据库。

## 核心文件

| 文件                | 功能                                         |
| ------------------- | -------------------------------------------- |
| `engine/tools.py` | 包装层：自动处理 conn/config/person 解析     |
| `engine/agent/`   | 底层实现：按域拆分到各模块（见`agent.md`） |

## 架构

```
Agent 调用: chat('biophilia', recent=50)
    ↓
tools.py 包装: _resolve('biophilia') → (conn, config, person)
    ↓
engine/agent/chat.py: agent_chat(conn, config, person, recent=50)
    ↓
返回: str (Markdown)
```

包装层只做一件事：把 `name: str` 解析为 `(conn, config, person)` 三元组，调用底层函数，最后 `conn.close()`。

## 工具速查表

### 数据获取（只读）

```python
from engine.tools import brief, chat, evidence, metrics, rank, status
from engine.tools import wiki_search, wiki_show, moments_stats
from engine.tools import brief_data, chat_data, message_context_data
```

| 函数              | 签名                                                                                         | 返回     | 用途                                                   |
| ----------------- | -------------------------------------------------------------------------------------------- | -------- | ------------------------------------------------------ |
| `brief`         | `(name, compact=False) -> str`                                                             | Markdown | 全局视图：事实+指标+事件+信号+Wiki推荐                 |
| `brief_data`    | `(name) -> dict`                                                                           | dict     | 结构化摘要，返回 `{status, data, meta}` 含 identity/metrics/events/signals 等 |
| `chat`          | `(name, *, recent=50, from_date=None, to_date=None, keyword=None, context_lines=0) -> str` | Markdown | 聊天记录，已标注"我"/对方名字                          |
| `chat_data`     | `(name, *, recent=50, from_date=None, to_date=None, keyword=None, context_lines=0) -> dict` | dict     | 结构化消息列表，每条含 id/sender_id/is_mine/timestamp/content |
| `message_context_data` | `(message_ids, before=20, after=20) -> dict`                                         | dict     | 根据消息 ID 获取前后上下文（不跨会话）                  |
| `evidence`      | `(name, section='all', since_date=None) -> str`                                            | Markdown | 事实档案（timeline/evaluations/notes/dates/all）       |
| `metrics`       | `(name) -> dict`                                                                           | dict     | 16 指标+neediness_penalty+interaction_pattern+动态信号 |
| `status`        | `(name) -> str`                                                                            | Markdown | 格式化的指标状态表                                     |
| `rank`          | `() -> str`                                                                                | Markdown | 全部联系人排名表                                       |
| `wiki_search`   | `(query) -> str`                                                                           | Markdown | 跨 Wiki/分析/KB 搜索                                   |
| `wiki_show`     | `(path, *, max_chars=50000) -> str`                                                        | str      | 读取材料文件全文                                       |
| `moments_stats` | `(name) -> dict`                                                                           | dict     | 朋友圈互动统计                                         |

### 数据写入

```python
from engine.tools import note, date, evaluate, events, save_analysis, save_from_markdown
from engine.tools import contact, exclude, failure, sticker
```

| 函数                   | 签名                                                          | 用途                               |
| ---------------------- | ------------------------------------------------------------- | ---------------------------------- |
| `note`               | `(name, text) -> str`                                       | 添加备注到事实档案                 |
| `date`               | `(name, date_text=None, location=None, rating=None) -> str` | 记录会面                           |
| `evaluate`           | `(name, text) -> str`                                       | 记录主观评估                       |
| `events`             | `(name, scan=False, disconnect_days=7) -> str`              | 检测销售事件（scan=True 写入档案） |
| `save_analysis`      | `(name, stage, confidence, reasoning, diagnosis, strategy, risks, ..., evidence_refs=None, metric_snapshot=None, data_window=None, changed_from_previous=None) -> str` | 保存分析结论到 YAML，可选证据引用和指标快照 |
| `save_from_markdown` | `(name, markdown_text) -> str`                              | 从结构化 Markdown 保存分析         |
| `contact`            | `(query, action='search', **kwargs) -> str`                 | 身份目录操作                       |
| `exclude`            | `(action='list', **kwargs) -> str`                          | 排除管理（list/add/remove）        |
| `failure`            | `(action='list', **kwargs) -> str`                          | 失败案例管理                       |
| `sticker`            | `(action='list', **kwargs) -> str`                          | 贴纸管理                           |

### 同步

```python
from engine.tools import sync, sync_person, sync_moments, weekly
```

| 函数                 | 签名                                                              | 用途                                   |
| -------------------- | ----------------------------------------------------------------- | -------------------------------------- |
| `sync`             | `(mode='incremental', session_id=None, meta_only=False) -> str` | 数据同步（**默认增量**）         |
| `sync_person`      | `(name, mode='incremental') -> str`                             | 按人名同步（**默认增量**）       |
| `sync_moments`     | `(name) -> str`                                                 | 同步朋友圈互动到事实档案               |
| `weekly`           | `(deep=False) -> str`                                           | 生成周报                               |
| `compare_analysis` | `(name) -> str`                                                 | 对比 latest 和 previous 分析结论的变化 |

**同步原则**：默认使用增量更新，尽量少用全量更新（`mode='full'`）。全量同步耗时长且通常不必要。

### 密钥管理

```python
from engine.tools import check_keys, fetch_keys
```

| 函数           | 签名                                  | 用途                                              |
| -------------- | ------------------------------------- | ------------------------------------------------- |
| `check_keys` | `() -> str`                         | 检查密钥是否已缓存（account_keys.json）           |
| `fetch_keys` | `(wechat_install_path=None) -> str` | ⚠️ 获取密钥（会重启微信，**不建议使用**） |

**密钥原则**：密钥通过 `account_keys.json` 持久化，WCD 启动时自动加载。`fetch_keys` 会重启微信要求扫码，频繁调用有封号风险，仅在密钥丢失时使用。

### 客户维护

| 函数                    | 签名                                   | 用途                                                   |
| ----------------------- | -------------------------------------- | ------------------------------------------------------ |
| `maintain_candidates` | `(max_people=10) -> list[Candidate]` | 筛选需要维护的客户（热度下降/意向未推进/高潜力） |
| `format_candidates`   | `(candidates) -> str`                | 格式化为 Markdown（含上次消息摘要、消息建议规则）      |

### 销售决策公式

```python
from engine.tools import sales_params, sales_bq, sales_bsp, sales_bws
from engine.tools import sales_pv, sales_action
```

| 函数                   | 签名                                                                   | 用途                                         |
| ---------------------- | ---------------------------------------------------------------------- | -------------------------------------------- |
| `sales_params`     | `(name, conn=None) -> dict`                                         | 自动计算全部可量化参数（auto + manual 提示） |
| `sales_bq`        | `(sp, fback, user_investment, pface) -> dict`                        | 购买意愿真实度（Buyer Intent）               |
| `sales_bsp`        | `(user_ddepth, target_ddepth, target_latency, user_latency) -> dict` | 商务势能（Business Social Potential）        |
| `sales_bws`        | `(gap_effect, cp_index, eev, scarcity_loss) -> dict`                 | 购买意向期（Buying Window Signal）            |
| `sales_pv`         | `(backstage, pface) -> dict`                                         | 成交期望值（Proposal Value）                 |
| `sales_action`     | `(bq, bsp, bws, bs=0.0, ev=0.5) -> dict`                            | 终极决策：报价/推进/培育/重置/维持            |

## 使用示例

```python
from engine.tools import brief, chat, wiki_search, sync_person

# 分析某人
sync_person('小溪')
print(brief('小溪', compact=True))
print(chat('小溪', recent=100))

# 搜索 Wiki
print(wiki_search('客户需求'))

# 读取 Wiki
from engine.tools import wiki_show
print(wiki_show('docs/wiki/wiki/entities/意向指标.md'))
```

## 工作流工具（Skill-MCP 融合）

```python
from engine.tools import skill_map, workflow_step
```

| 函数           | 签名                                     | 用途                                           |
| -------------- | ---------------------------------------- | ---------------------------------------------- |
| `skill_map`   | `(tool_name=None) -> str`                | 查询工具与 Skill 的双向映射，返回下一步建议。不传 tool_name 返回全部工具概览 |
| `workflow_step` | `(workflow, step=None) -> str`           | 按步骤执行工作流，返回当前步骤详情和下一步指引 |

**工作流列表**：

| 工作流 | 名称 | 步骤数 |
|--------|------|--------|
| `analysis` | 客户分析完整流程 | 13 步 |
| `emergency_reply` | 紧急回复流程 | 4 步 |
| `weekly` | 周报流程 | 2 步 |
| `maintain` | 维持关系流程 | 4 步 |

**使用示例**：

```python
# 查看分析流程概览
workflow_step('analysis')

# 获取第0步详情
workflow_step('analysis', 0)

# 查询工具映射
skill_map('person_brief')

# 查看所有工具概览
skill_map()
```

## 禁止事项

| 禁止                                      | 正确做法                                   |
| ----------------------------------------- | ------------------------------------------ |
| 直接用`sqlite3` 查 `data/raw/core.db` | 用`chat()` / `brief()` / `metrics()` |
| 自己写 SQL                                | 用`engine.tools` 中的函数                |
| 把原始记录导出到文件                      | 用`chat()` 获取已格式化的 Markdown       |
| 向`data/input/` 写入文件                | 该目录仅用于用户手动放置截图               |
| 调用 LLM API                              | Agent 自己就是 LLM                         |
