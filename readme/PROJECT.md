# SalesCRM 项目文档

> 最后更新：2026-06-30
> 基于当前代码状态重写

---

## 一、项目概述

SalesCRM 是一个本地优先的 AI 销售客户分析助手。系统从微信聊天记录、客户事实档案和销售知识库中获取上下文，用 Python 工具完成数据同步、身份解析、指标计算和事实读写，再由 Agent 负责综合判断客户阶段、意向强度、跟进时机和下一步话术。

**核心原则**：代码负责数据，Agent 负责推理。

**当前定位**：

- 不是 Salesforce、纷享销客这类公司级 CRM 的替代品。
- 不是群发、裂变、自动回复工具。
- 是个人或小团队销售顾问的本地客户分析助手，把聊天记录变成可分析、可追踪、可行动的销售上下文。

**架构**（Wiki 主轴 + 公式辅助参考，详见 `exchange/architecture/架构.md`）：

```text
原始知识文件 → 知识构建管道 → OKF 知识库（推理主轴）────┐
   (视频/PDF/课程/经验)         (OCR/转写/MD→OKF)        │
                                                         │
微信聊天 → 同步管道 → 指标/事件/排名 ─┬─ 事实档案 ──────┼─→ Agent 推理
   (WCD/WeFlow API)                  │  (data/customers/)│   ① 读 Wiki 找方法论
                                     │                   │   ② 查事实档案
                                     └─ 原始数据 ────────┤   ③ 看实时数据
                                                         │   ④ 核验公式
              公式（辅助参考，chat-skills 遗产） ←────────┤
              ├─ 通用战态：IVI/SPE/EWS/IS/Gap_Effect/EEV/CS/action
              └─ 销售专属：BQ/BSP/BWS/PV/sales_action
              标注 Wiki 依据做软关联，不机械套阈值
                                                         ▼
                                            状态分析/策略/话术/应急
```

**MCP 暴露**：53 个工具（23 只读 + 15 写入 + 15 公式），通过 FastMCP stdio 协议复用 `engine/tools.py`，详见 [mcp.md](mcp.md)。

**数据来源**：

```text
WeChatDataAnalysis (WCD) 或 WeFlow
  → HTTP API
  → engine/importers/* 同步管道
  → data/raw/core.db (SQLite)
  → engine/analyzers/* 指标、排名、事件检测
  → engine/tools.py Agent 工具入口
```

### 1.1 适用场景与定位

| 场景                |   匹配度   | 说明                                                   |
| ------------------- | :--------: | ------------------------------------------------------ |
| 个人/小团队销售顾问 | ★★★★★ | 微信是主战场，需要量化客户意向，自动提醒跟进           |
| 私域/社群运营       | ★★★★☆ | 大量联系人需要自动标签和活跃度监控，但公式偏重 B2B 销售 |
| SaaS 销售（B2B）    | ★★★☆☆ | 数据管道有价值，但 B2B 决策周期长，指标需要单独调参    |
| 大客户销售团队      | ★★☆☆☆ | 决策链复杂、需对接企业 CRM，单人微信模式不够用         |
| 电商/快消销售       | ★★★☆☆ | 回复频率指标在低客单价场景更有用，但知识库偏 B2B       |

**定位**：

- **不是** Salesforce / 纷享销客 / Pipedrive 的替代品——它不解决公司级销售流程管理
- **不是** 微信管理工具（WeTool 等）——它不做群发、裂变、自动回复
- **是** 一个个人销售助理——把微信聊天记录变成可分析的结构化数据，用 Agent 辅助决策

### 1.2 同类工具对比

| 维度                 | SalesCRM               | Salesforce / 纷享销客 | WeTool / 微伴    | 飞书多维表格 | 纯凭记忆 |
| -------------------- | ---------------------- | --------------------- | ---------------- | ------------ | -------- |
| **数据来源**   | 微信聊天记录           | 手动录入              | 微信通讯录/群聊  | 手动录入     | 大脑     |
| **意向量化**   | 辅助参考公式 + Wiki 主轴 | 靠销售自己填          | 无               | 无           | 凭感觉   |
| **自动化程度** | 增量同步+Agent推理     | 全靠人维护            | 群发/拉群工具    | 模板化       | 无       |
| **销售方法论** | 知识库 + Agent 检索    | 无内置                | 无               | 无           | 靠经验   |
| **对接微信**   | 原生支持（WCD/WeFlow） | 不支持                | 支持（官方接口） | 不支持       | 不适用   |
| **数据安全**   | 全本地                 | 上云                  | 上云             | 上云         | 无       |
| **部署成本**   | 本地搭环境             | 付费订阅              | 付费订阅         | 免费         | 0        |
| **团队协作**   | 无                     | 完整                  | 基础             | 完整         | 不适用   |

**关键差异总结**：

- **相比 Salesforce 等传统 CRM**：SalesCRM 不要求销售手动填数据，数据自动从微信进来。代价是没有完整的销售流程管理和团队协作能力。
- **相比 WeTool/微伴**：SalesCRM 不做群发和裂变，做的是分析。WeTool 解决"触达效率"，SalesCRM 解决"判断准确度"。
- **相比飞书多维表格**：飞书表格需要自己粘贴记录，SalesCRM 自动同步。但飞书协作方便。
- **相比纯凭记忆**：客户多的时候必忘，SalesCRM 自动计算沉默期、检测事件、排名热度。但需要信任它的指标。

---

## 二、已实现功能

### 2.1 数据同步

从 WCD 或 WeFlow 同步微信数据到本地 SQLite。通过 `data/system/config.yaml` 的 `weflow.backend` 选择后端。

| 功能 | 说明 |
| --- | --- |
| 联系人同步 | 拉取联系人昵称、备注、头像、标签等元数据 |
| 会话同步 | 拉取私聊、群聊等会话元数据 |
| 消息同步 | 默认增量同步，支持全量重拉和单会话同步 |
| 朋友圈同步 | 拉取朋友圈动态和互动数据 |
| 截图 OCR 导入 | 从截图导入非微信平台聊天记录 |
| checkpoint 机制 | 基于 watermark 增量同步，避免重复拉取 |

主要数据库表：

| 表 | 说明 |
| --- | --- |
| `contacts` | 联系人基础信息 |
| `conversations` | 会话元数据 |
| `messages` | 聊天消息 |
| `attachments` | 附件记录 |
| `moments` | 朋友圈动态 |
| `moment_interactions` | 朋友圈互动 |
| `sync_state` | 同步水位 |
| `sync_log` | 同步日志 |
| `people` | 身份目录中的客户 |
| `contact_accounts` | 客户账号映射 |
| `contact_aliases` | 客户别名 |
| `contact_identity_log` | 身份操作日志 |
| `schema_version` | 数据库迁移版本 |

**数据源扩展（设计阶段）**：

| 数据源   | 接入方式             | 同步内容                   | 状态 |
| -------- | -------------------- | -------------------------- | ---- |
| 微信聊天 | HTTP API → 同步管道 | 客户微信沟通记录           | ✅ 已实现 |
| 企业微信 | 企微 API             | 工作沟通记录               | ❌ 待实现 |
| CRM 系统 | CRM API / CSV 导入   | 客户信息/商机阶段/成交记录 | ❌ 待实现 |
| 邮件     | IMAP / 邮件 API      | 邮件往来                   | ❌ 待实现 |
| 通话录音 | 转录 → ASR           | 电话沟通内容               | ❌ 待实现 |
| 面谈笔记 | 手动记录 / OCR 导入  | 线下见面记录               | ❌ 待实现 |

**商机管理表（设计阶段）**：

| 表                | 主键      | 说明                                             | 状态 |
| ----------------- | --------- | ------------------------------------------------ | ---- |
| `deals`         | id (TEXT) | 商机/交易（客户ID/金额/阶段/预计关闭日期）       | ❌ 待实现 |
| `deal_stages`   | id (TEXT) | 商机阶段变更历史                                 | ❌ 待实现 |

### 2.2 客户阶段定义

```
潜客(Lead) → 初步接触 → 需求确认 → 方案展示 → 谈判/报价 → 成交 → 售后/复购
                                   ↓                    ↓
                               流失/沉默            流失/沉默
```

| 销售阶段  | 核心任务                   |
| --------- | -------------------------- |
| 潜客获取  | 获取联系方式，建立初步连接 |
| 初步接触  | 建立信任，展示产品价值     |
| 需求确认  | 深入了解痛点，确认决策链   |
| 方案展示  | 定制方案，逐步确认意向     |
| 谈判/报价 | 价格谈判，异议处理，逼单   |
| 成交      | 签合同，收款               |
| 售后/复购 | 售后跟进，增购/转介绍      |

### 2.3 身份目录

`engine/identity/` 实现 Person → Account → Alias 三层映射。一个客户可以有多个微信号、多个昵称和多个业务别名。

| 能力 | 说明 |
| --- | --- |
| 自动初始化 | 从 contacts/conversations 创建客户身份 |
| 模糊搜索 | 支持名字、备注、昵称、wxid、person_id 查询 |
| 别名管理 | 支持 display_name、remark、nickname、manual 等别名 |
| 账号绑定 | 将多个微信账号绑定到同一客户 |
| 合并 | 合并重复客户身份 |
| 审计 | 检测疑似重复、孤立账号、未归属联系人 |

所有按客户名查询的工具都通过身份目录解析，禁止绕过工具直接查数据库。

### 2.4 指标引擎

`engine/analyzers/metrics.py` 计算客户互动指标、动态信号和销售特有指标。

**15 个指标的本质**：这 15 个指标是**辅助指标**（结构化数字摘要），不是精确评分系统。它们的来源是 Wiki 知识库总结 + GitHub 公开方法论 + 历史案例反馈，本质上是把非结构化聊天记录压缩成 Agent 好消化的结构化数字，跟 embedding vector 同类——提供量化视角供 Agent 参考，但不主导决策。权重是经验启发值，部分已通过实际案例校准，完整回测校准是未来工作。

| 指标              | 含义                           | 权重 |
| ----------------- | ------------------------------ | ---- |
| `fback`           | 客户/销售回复字数比            | 0.10 |
| `rlatency`        | 双方回复速度比                 | 0.10 |
| `fback_quality`   | 回复质量（正向情绪+追问-敷衍） | 0.10 |
| `qscore_personal` | 个性化问题比例                 | 0.10 |
| `trend`           | composite 周变化               | 0.10 |
| `escore_volatility` | 情绪波动（会话间标准差）     | 0.08 |
| `moments`         | 朋友圈互动频率                 | 0.06 |
| `qscore_functional` | 工具化/功能性问题比例       | 0.05 |
| `rlatency_context` | 慢回时有解释的比例           | 0.05 |
| `msg_volume_trend` | 消息量周变化率               | 0.05 |
| `latency_trend`   | 回复速度周变化率               | 0.05 |
| `recent`          | 最后消息距今天数               | 0.05 |
| `active_days`     | 近 30 天活跃天数               | 0.04 |
| `escore`          | 情绪表达比例                   | 0.05 |
| `msg_count`       | 消息总数（对数归一化）         | 0.02 |

**乘法惩罚**：neediness_penalty（0.4-1.0），消息量比 > 2 或发起频率 > 70% 时触发。

**意向等级**：强意向(>=0.70) / 中意向(>=0.50) / 弱意向(>=0.30) / 冷淡(>=0.15) / 无信号(<0.15)

**互动模式**：

| 模式            | 含义                     | 销售策略                 |
| --------------- | ------------------------ | ------------------------ |
| buyer           | 客户主动了解、追问细节   | 加速推进，及时报价       |
| evaluator       | 客户理性比较、问竞对差异 | 强化差异化优势，提供案例 |
| free_consulting | 客户只问不买，白嫖信息   | 控制信息输出，设门槛     |
| silent          | 客户不回复、不拒绝       | 改变触达方式或冷冻       |

**动态信号**：session_recency（最近活跃）、momentum（7天动量）、initiation_source（谁发起）

销售特有指标（`compute_sales_metrics`）：

| 指标 | 含义 |
| --- | --- |
| `meeting_count` | 见面、电话、会议相关信号 |
| `budget_known` | 是否讨论过预算或价格 |
| `decision_chain` | 是否提到决策人、采购流程 |
| `urgency` | 紧迫性信号 |
| `competition` | 是否提到竞品或对比 |

### 2.5 Wiki 知识库（推理主轴）

`docs/wiki/` 是 SalesCRM 的**推理主轴**，不是补充参考。Agent 在分析客户前，先检索 Wiki 找方法论框架，再结合数据下判断。

| 维度 | 说明 |
| --- | --- |
| 格式 | OKF（Open Knowledge Format）：YAML frontmatter + 结构化 Markdown + `[[条目]]` 双向链接 |
| 内容 | 78 entities（销售方法论、客户心理学、谈判技巧等）+ 14 scenarios（典型销售场景） |
| 检索 | `wiki_search(query)` 五维度评分（title/keyword/tag/stage/skill）+ 别名扩展，不依赖 embedding |
| 读取 | `wiki_show(path)` 安全读取全文，自动截断超长内容 |
| 渐进披露 | 4 种 task_type 预算（default/reply/deep/search）控制返回内容量，按需检索不超上下文 |
| 适用场景 | SPIN、MEDDIC、价格异议、客户沉默激活、竞品应对、需求确认、谈判心理学等 |

**Agent 使用方式**：每个判断都引用 Wiki 条目作为依据。例如 `[[价格异议应对]]` 告诉 Agent 异议分三类（预算不足/谈判策略/借口拒绝），先判断类型再回应；`[[客户意向判断]]` 给出回复率 >0.6 为正向的参考阈值。Agent 不是机械套用，而是结合实时数据核验。

详细风格参照 `exchange/architecture/example_analysis_sales.md`，公式数值只在"数据全貌"表出现一次，策略全部回指 Wiki 条目。

### 2.6 辅助参考：公式与指标

公式是 chat-skills 遗产的独立体系，通过标注 Wiki 依据做**软关联**（非派生）。Agent 用公式核验判断，不机械套阈值。详见 [formulas.md](formulas.md)。

| 类别 | 公式 | Wiki 依据 | 定位 |
| --- | --- | --- | --- |
| 通用战态（9 个） | `formula_ivi`/`spe`/`ews`/`is`/`gap_effect`/`eev`/`cs`/`action`/`params` | IVI/SPE/EWS/Gap_Effect 已标 | 辅助参考 |
| 销售专属（6 个） | `sales_bq`/`bsp`/`bws`/`pv`/`action`/`params` | BQ/BSP/BWS 已标 | 辅助参考 |

调用示例：`sales_action(bq, bsp, bws, pv)` 返回 `bargain/push/nurture/reset/maintain`。结果仅作参考视角，最终决策由 Agent 基于 Wiki + 事实档案 + 实时数据综合判断。

### 2.7 事件检测

`engine/analyzers/events.py` 和 Agent 信号检测模块从聊天记录中识别关键销售事件。

| 事件类型 | 说明 |
| --- | --- |
| `FIRST_CHAT` | 首次聊天 |
| `DISCONNECT` | 连续 N 天无消息 |
| `RECONNECT` | 断联后恢复联系 |
| `FREQUENCY_UP` | 近期消息频率上升 |
| `FREQUENCY_DOWN` | 近期消息频率下降 |
| `REQUIREMENT_CONFIRM` | 需求确认信号 |
| `DECISION_MAKER_APPEAR` | 决策人出现 |
| `PROPOSAL_SENT` | 方案或报价发送 |

`events("客户名", scan=True)` 会把检测到的事件写入事实档案的 `## 关系时间线` 段落。该段落名称来自历史实现，在 SalesCRM 中表示客户沟通/商机时间线。

### 2.8 事实档案

事实档案由 `engine/facts/people_archive.py` 管理，存储在：

```text
data/customers/<显示名>__<person_id>.md
data/facts/self/<显示名>__<person_id>.md
```

事实层只记录客观事实，不承担当前判断。分析结论存储在 `data/outputs/analysis/`，由 `save_analysis()` 或 `save_from_markdown()` 写入。

常用写入工具：

| 工具 | 用途 |
| --- | --- |
| `note(name, text)` | 添加客户备注 |
| `date(name, date_text, location, rating)` | 记录会面、电话、演示或重要沟通 |
| `evaluate(name, text)` | 保存一条主观评估到 outputs/evaluations |
| `events(name, scan=True)` | 检测并写入关键事件 |
| `sync_moments(name)` | 同步朋友圈互动到事实档案 |

### 2.9 排名、周报和客户维护

| 工具 | 用途 |
| --- | --- |
| `rank()` | 全部联系人排名 |
| `weekly(deep=False)` | 生成周报和排名快照 |
| `maintain_candidates(max_people=10)` | 筛选需要维护或跟进的客户 |
| `format_candidates(candidates)` | 格式化维护候选人列表 |

**客户排名视图**：

| 排名视图 | 条件                  | 用途                 |
| -------- | --------------------- | -------------------- |
| 热客榜   | composite > 0.5       | 优先跟进的高意向客户 |
| 沉默榜   | recent > 7 天         | 需要重新激活的客户   |
| 咨询模式榜 | free_consulting 模式 | 仅咨询不成交的客户   |
| 紧急榜   | urgency 高 + 竞对威胁 | 需要紧急推进的客户   |

### 2.10 Agent 分析风格

Agent 输出遵循 `exchange/architecture/example_analysis_sales.md` 的八段式结构：

1. **场景理解** — 复述客户情境，引用相关 Wiki 条目
2. **数据全貌** — 表格列出关键数据 + Wiki 解读列（公式数值只在此出现一次）
3. **关键信号分析** — 积极信号/消极信号分列，每条带 Wiki 依据
4. **Wiki 框架诊断** — 用多个 Wiki 条目交叉验证判断
5. **具体操作** — 每步操作都引用 Wiki 方法论
6. **绝对不要做** — 列出禁忌及其 Wiki 依据
7. **核心风险** — 识别失败路径和应对
8. **底层判断** — 用 Wiki 框架做最终结论，公式作为辅助参考

**核心特征**：每个判断都引用 Wiki 条目作为依据；公式数值（BQ=0.78 等）只在数据全貌表出现一次；策略全部回指 Wiki 条目，不机械套用公式阈值。

---

## 三、Agent 工具契约

所有对数据的访问都应通过 `engine.tools`。

### 3.1 工具分层

| 层 | 工具 | 返回 | 说明 |
| --- | --- | --- | --- |
| 数据读取 | `brief`、`chat`、`evidence`、`metrics`、`status`、`rank`、`wiki_search`、`wiki_show`、`moments_stats` | str 或 dict | 只读，可安全重试 |
| 结构化读取 | `brief_data`、`chat_data`、`message_context_data` | dict | 推荐给 Agent 内部精细分析使用 |
| 数据写入 | `note`、`date`、`evaluate`、`events(scan=True)`、`save_analysis`、`save_from_markdown` | str 或 Path | 有副作用 |
| 身份管理 | `contact`、`exclude`、`failure`、`sticker` | str | 修改身份目录或辅助数据 |
| 同步 | `sync`、`sync_person`、`sync_moments` | str | 从外部数据源写入本地数据库 |
| 计算（辅助参考） | `sales_params`、`sales_bq`、`sales_bsp`、`sales_bws`、`sales_pv`、`sales_action`、`formula_*` | dict | 辅助参考视角，Agent 核验而非套用 |

### 3.2 权限规范

| 操作 | 规则 |
| --- | --- |
| 只读工具 | 可直接调用 |
| `note`、`date`、`evaluate` | 可直接追加，事后可手动删除 |
| `save_analysis`、`save_from_markdown` | 覆盖 latest 前应告知用户 |
| `events(scan=True)` | 先展示检测结果更稳，再写入 |
| `contact(alias/link)` | 可直接执行并说明结果 |
| `contact(merge)` | 不可逆，必须先让用户确认 |
| `sync`、`sync_person` | 可直接执行，报告同步结果 |
| `fetch_keys` | 会重启微信，不应主动调用，除非用户明确要求 |

### 3.3 禁止事项

| 禁止 | 正确做法 |
| --- | --- |
| 直接用 `sqlite3` 查 `data/raw/core.db` | 用 `chat()`、`brief()`、`metrics()` |
| 自己写 SQL 查询消息或联系人 | 用 `engine.tools` |
| 导出原始聊天记录文件 | 用 `chat()` 获取格式化 Markdown |
| 向 `data/input/` 写入文件 | 该目录只用于用户手动放截图 |
| 调用外部 LLM API | Agent 自己负责推理 |

### 3.4 数据层优先级（两张表）

数据使用分两层理解：**操作顺序**回答"按什么顺序查"，**冲突裁决**回答"谁说了算"。

#### 表 1：Agent 操作顺序（推理步骤）

| 步骤 | 数据来源 | 工具 | 目的 |
|------|---------|------|------|
| ① | OKF 知识库 | wiki_search / wiki_show | 找方法论框架（推理主轴） |
| ② | 事实档案 | evidence | 查阅长期记忆（客观事实） |
| ③ | 实时数据 | brief / chat / metrics / status | 看当前事实（最新状态） |
| ④ | 公式核验 | sales_params / sales_* | 量化视角辅助参考 |

> 这是**操作顺序**，不是优先级。Agent 先找方法论再动手分析。

#### 表 2：冲突裁决规则（证据链）

当多个数据源矛盾时，按以下优先级裁决：

| 优先级 | 数据来源 | 性质 |
|--------|---------|------|
| 1（最高） | 实时数据（brief/chat/metrics） | 当前事实，不可推翻 |
| 2 | 事实档案（evidence） | 客观记录，可信 |
| 3 | OKF 知识库（wiki_search） | 方法论依据，提供解释框架 |
| 4 | 事件检测（events） | 从数据推导，基本可信 |
| 5 | 公式计算（sales_*） | 量化视角，有启发但需核验 |
| 6（最低） | 历史分析（data/outputs/analysis/） | 过去的观点，可能已过时 |

**规则**：当低层数据与高层矛盾时，以高层为准。公式结果只能作为"视角"，不能推翻事实和 Wiki 知识。历史分析仅用于"上次分析认为 X，现在数据变了"的对比叙述。

---

## 四、常用工作流

### 4.1 分析客户

```python
from engine.tools import sync_person, brief, chat, metrics, sales_params

sync_person("张三")
overview = brief("张三", compact=True)
recent_chat = chat("张三", recent=100)
m = metrics("张三")
params = sales_params("张三")
```

Agent 输出时应包含：

- 当前客户阶段
- 关键证据
- 意向强度
- 当前风险
- 下一步动作
- 可直接发送的话术

### 4.2 判断是否报价

```python
from engine.tools import sync_person, sales_params, sales_bq, sales_bsp, sales_bws, sales_pv, sales_action

sync_person("张三")
params = sales_params("张三")
# Agent 根据聊天内容补齐 manual 参数，再调用公式。
```

不要只看一个分数。报价判断应同时看需求明确度、预算/价格讨论、决策链、竞品压力、最近活跃度和关系势能。

### 4.3 记录客户信息

```python
from engine.tools import note, date

note("张三", "客户提到预算审批需要老板确认")
date("张三", date_text="2026-06-30", location="线上演示", rating=4)
```

事实档案写客观事实；策略判断应写到分析结论。

### 4.4 周报和客户维护

```python
from engine.tools import sync, weekly, maintain_candidates, format_candidates

sync()
report = weekly()
candidates = maintain_candidates(max_people=10)
print(format_candidates(candidates))
```

### 4.5 沉默客户激活

```
用户："看看我有哪些沉默客户"

Agent 执行：
1. rank()                                   # 查看排名
2. 过滤 recent > 7 天的客户
3. 输出沉默客户列表 + 激活建议
```

### 4.6 紧急回复支持

```
用户："客户发了'价格有点贵'怎么回"

Agent 执行：
1. sync_person("张三")                    # 同步最新消息
2. chat("张三", recent=30)                 # 获取最近聊天
3. metrics("张三")                         # 获取当前指标
4. wiki_search("价格异议 应对")              # 找相关框架
5. 结合数据 + 框架，给出一条可直接发送的回复
```

---

## 五、目录结构

```text
SalesCRM/
├── engine/
│   ├── tools.py              # Agent 工具统一入口
│   ├── formulas.py           # 公式基类（_validate_params 等）
│   ├── formulas_love.py      # 通用战态公式（IVI/SPE/EWS 等 9 个，辅助参考）
│   ├── formulas_sales.py     # 销售专属公式（BQ/BSP/BWS/PV 等 6 个，辅助参考）
│   ├── config.py             # 配置和目录常量
│   ├── agent/                # Agent 工具实现层
│   ├── analyzers/            # 指标、排名、事件、周报
│   ├── facts/                # 事实档案和失败案例
│   ├── identity/             # 身份目录
│   ├── importers/            # WCD/WeFlow/OCR 同步导入
│   ├── knowledge/            # Wiki 知识库检索（推理主轴）
│   └── models/               # dataclass 数据模型
├── .claude/skills/
│   ├── sales-crm.md          # SalesCRM 主入口
│   ├── chat-analyzer.md      # 聊天深度分析
│   └── person-info.md        # 客户事实档案管理
├── docs/wiki/                # OKF 知识库（推理主轴，78 entities + 14 scenarios）
├── data/
│   ├── raw/core.db           # 本地 SQLite 数据库
│   ├── system/config.yaml    # 本地配置和 token
│   ├── customers/            # 客户事实档案
│   ├── facts/self/           # 自我或本账号档案
│   └── outputs/              # 分析、周报、排名、评估输出
├── readme/                   # 模块文档
│   ├── PROJECT.md            # 项目总览（Wiki 主轴 + 公式辅助参考架构）
│   ├── formulas.md           # 公式参考（辅助视角，含演进链条）
│   ├── facts.md              # 事实档案（evidence/evaluation 分层 + 自检清单）
│   ├── mcp.md                # MCP 工具文档（53 个工具）
│   ├── architecture_correction_completed.md  # 架构矫正完成记录
│   ├── future_formula_wiki_metadata.md       # P6 未来计划：公式-Wiki 结构化元数据
│   └── ...                   # 其他模块文档
├── tools/                    # 文档和标注辅助工具
├── tests/                    # 单元测试
└── contest/                  # TRAE 比赛材料
```

---

## 六、当前风险和边界

### 6.1 数据源可持续性

WCD/WeFlow 依赖微信本地数据和外部 API 服务，微信版本变化可能导致同步失效。应保留截图 OCR、手动导入或历史数据备份作为兜底路径。

### 6.2 指标权重仍需校准

当前 BQ/BSP/BWS/PV 和 composite 分数是启发式决策辅助，不是成交概率模型。真实业务中应结合成交历史、行业周期和销售阶段继续校准。

### 6.3 B2B 场景需谨慎解释沉默

B2B 客户长时间不回复不一定代表无意向，可能处于内部审批、预算排期或多方评估。Agent 必须结合事实档案、决策链和阶段判断，不应机械套用 `recent > 7 天`。

### 6.4 个人工具优先于产品化

当前系统最适合先做个人或小团队本地销售分析助手。若要产品化，需要补齐团队协作、权限管理、数据合规、企业微信/CRM 正式接入和前端体验。

### 6.5 公式权重的来源不透明

BQ、BSP、BWS 等公式的权重和阈值目前多为经验启发值，缺少标注来源（经验值/历史数据拟合/理论推导）。建议在公式旁注明依据，后续有真实销售成交数据后可用历史数据回归校准权重。

### 6.6 冷启动问题

新用户接入系统时没有历史消息，排名和指标会为空。建议首次全量同步后自动生成"客户活跃度基线"，用前 7 天数据做默认阈值；或提供快速导入路径，至少导入历史聊天记录。

### 6.7 composite 分数定义需明确

多处使用 composite 作为客户排序依据（热客榜 threshold、意向等级），但 composite 的具体计算方式、及其与 BQ/BSP 等分项指标的关系需要更明确的文档说明。

---

## 七、外部依赖

| 依赖 | 用途 | 是否必须 |
| --- | --- | --- |
| `pyyaml` | 配置和 YAML 输出 | 必须 |
| `pytest` | 单元测试 | 开发 |
| `rapidocr-onnxruntime` | 截图 OCR | 可选 |
| `Pillow` | 图片处理 | 可选 |

同步管道和分析器主要依赖 Python 标准库。
