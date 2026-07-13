# SalesCRM MCP 服务器

> **状态**：已完工 — 62 个工具全部注册，全量验收通过
> **最后更新**：2026-07-14

---

## 一、概述

MCP（Model Context Protocol）服务器将 `engine/tools.py` 的函数通过标准协议暴露给 AI 代理（Claude Desktop、Cursor、Windsurf 等）。

```
Claude Desktop / Cursor / Windsurf
            │
            │  (MCP stdio protocol)
            ▼
    ┌───────────────┐
    │  MCP Server   │  ← mcp_server/
    │  (FastMCP)    │
    └───────┬───────┘
            │  Python 函数调用
            ▼
    ┌───────────────┐
    │ engine/tools.py│
    └───────┬───────┘
            ▼
    engine/analyzers/ + engine/agent/ + engine/knowledge/
```

**设计原则**：MCP 是一层薄包装，不重复实现业务逻辑，直接调用 `engine/tools.py` 中的函数。

---

## 二、技术选型

| 选项 | 选择 |
|------|------|
| MCP 框架 | **FastMCP**（3.x），`mcp.tool()(fn)` 注册模式 |
| 传输方式 | **stdio**（本地运行） |
| 依赖 | `fastmcp>=2.0`、`pydantic>=2.7` |

---

## 三、目录结构

```
mcp_server/
├── __init__.py
├── server.py                # FastMCP 入口，注册 62 个工具
├── tools_read.py            # 只读工具（26 个，含 wiki_context/weflow_status）+ wcd_start/weflow_start（写入）
├── tools_formula.py         # 公式工具（15 个：9 战态 + 6 销售）
├── tools_guide.py           # 使用指南工具（1 个，11 个主题）
├── README.md                # 使用说明
├── QUALITY_CHECK.md         # 质量自检报告
├── TOOL_MAPPING.md          # 工具映射表
├── ISSUES.md                # 问题记录
└── tests/
    ├── __init__.py
    ├── conftest.py           # 测试夹具
    └── test_final.py         # 全量验收测试（10 项）
```

---

## 四、配置与启动

### Claude Desktop 配置

```json
{
  "mcpServers": {
    "salescrm": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "E:/Code/SalesCRM",
      "env": {
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

### 启动验证

```bash
python -X utf8 -m mcp_server.server
```

---

## 五、工具清单（62 个）

> **Wiki 工具优先**：`wiki_context` 是 Agent 推理的第一依据（批量建框架主入口），分析前先检索 Wiki 找方法论框架。`wiki_search` + `wiki_read` 保留用于精确单页钻取。
> **使用指南**：`guide` 工具提供 11 个主题的操作指南（分析流程/报告模板/方法论/权限规范等），Agent 不确定操作流程时调用。

### 5.1 Phase 1 — 核心工具（8 个）

| 工具名 | 说明 | 类型 |
|--------|------|------|
| `wiki_search` | **搜索 Wiki 知识库（Agent 推理第一依据，主轴）** | 只读 |
| `person_brief` | 客户简要信息（身份、指标、事件、信号、最近消息） | 只读 |
| `person_chat` | 聊天记录（按日期分组，标注"我"/"对方"） | 只读 |
| `person_metrics` | 客户关系指标（回复率、回复速度、情绪评分等） | 只读 |
| `person_rank` | 所有客户的商务热度排名 | 只读 |
| `person_status` | 当前状态快照（精简版指标） | 只读 |
| `person_note` | 添加客户备注到事实档案 | 写入 |
| `person_date_record` | 记录会面信息 | 写入 |

### 5.2 Phase 2 P0 — 即时补齐（4 个）

`wiki_context`（只读，**【推荐·Wiki 主入口】批量构建 Wiki 知识上下文**）、`wiki_read`（只读，Wiki 全文读取，精确单页钻取）、`person_sync`（写入）、`person_save_analysis`（写入）

### 5.3 Phase 2 P1 — 已实现工具（15 个）

**只读（10 个）：** `person_timeline`、`person_signals`、`person_evidence`、`person_compare`、`weekly_report`、`person_moments_stats`、`maintain_list`、`events_scan`、`wcd_status`、`weflow_status`

**写入（5 个）：** `events_save`、`person_evaluate`、`system_sync`、`wcd_start`（启动 WCD 后端进程）、`weflow_start`（启动 WeFlow 后端进程）

### 5.4 Phase 2 P2 — 拆分工具（15 个）

**只读（6 个）：** `contact_search`、`sticker_scan`、`sticker_list`、`exclude_list`、`failure_list`、`message_context`

**写入（9 个）：** `contact_alias`、`contact_alias_remove`、`contact_merge`（不可逆）、`sticker_label`、`exclude_add`、`exclude_remove`、`failure_add`、`save_from_markdown`、`sync_moments`

### 5.5 Phase 3 P3 — 公式工具（15 个，辅助参考）

> **定位**：公式是 chat-skills 遗产的辅助参考视角，Agent 核验而非套用。阈值非硬规则，最终决策由 Agent 基于 Wiki + 事实档案 + 实时数据综合判断。详见 `readme/formulas.md`。

**通用战态公式（9 个，辅助参考）：** `formula_get_params`、`formula_calc_ivi`（Wiki 依据：`[[购买意向指标]]`）、`formula_calc_spe`（`[[框架]]`）、`formula_calc_ews`（`[[窗口识别]]`）、`formula_calc_is`、`formula_calc_gap_effect`（`[[情绪落差（GapEffect）]]`）、`formula_calc_eev`、`formula_calc_cs`、`formula_calc_action`

**销售专属公式（6 个，辅助参考，SalesCRM 独有）：** `sales_get_params`、`sales_calc_bq`（`[[购买意向指标]]`）、`sales_calc_bsp`（`[[框架]]`）、`sales_calc_bws`（`[[窗口识别]]`）、`sales_calc_pv`、`sales_calc_action`

### 5.6 使用指南工具（1 个）

| 工具名 | 参数 | 说明 | 类型 |
|--------|------|------|------|
| `guide` | `topic` | 获取使用指南和工作流文档。11 个主题：getting-started / workflow/analysis / report-template / methodology / rules/evidence / rules/permissions / rules/reply / workflow/maintain / reference/sync / reference/formula / reference/stickers。支持中文别名 | 只读 |

### 5.7 工作流工具（2 个）

| 工具名 | 说明 | 类型 |
|--------|------|------|
| `skill_map` | 查询工具与 Skill 的双向映射，返回下一步建议 | 只读 |
| `workflow_step` | 按步骤执行工作流，返回当前步骤详情和下一步指引 | 只读 |

### 5.8 系统配置工具（2 个）

| 工具名 | 说明 | 类型 |
|--------|------|------|
| `get_backend` | 获取当前后端配置（WCD/WeFlow） | 只读 |
| `set_backend` | 设置后端配置 | 写入 |

### 5.9 永不暴露

| 函数 | 原因 |
|------|------|
| `fetch_keys` | 会重启微信并要求扫码，AI 无法完成 |

---

## 六、核心设计决策

### 6.1 返回格式

所有只读工具返回 Python dict（非 Markdown 字符串），AI 解析零歧义。使用 `_data` 变体函数（`brief_data`、`chat_data`、`rank_data` 等）。

### 6.2 确认语义：三级操作

| 操作类型 | 确认需求 | 示例 |
|---------|---------|------|
| **只读** | 不需要确认 | brief、chat、rank、metrics |
| **追加写入** | 直接执行 | note、date、evaluate |
| **不可逆/覆盖** | confirm + 风险提示 | merge、save_analysis |

### 6.3 密钥安全

`fetch_keys` 永不暴露。`wcd_status` 仅做只读状态查询，密钥失效时返回 suggestion 提示用户手动处理。

### 6.4 参数校验

所有公式参数 clamp 到 [0, 1] 范围，超出范围自动截断并返回 `param_warnings`（action 类函数除外）。

---

## 七、错误处理

```python
# 联系人不存在
{"error": "PERSON_NOT_FOUND", "message": "未找到联系人: xxx", "suggestion": "使用 person_rank() 查看所有联系人"}

# 工具执行失败
{"error": "TOOL_ERROR", "message": "xxx 执行失败: ...", "suggestion": "查看工具描述确认参数格式"}
```

---

## 八、验收结果

| # | 条件 | 结果 |
|---|------|------|
| 1 | MCP 服务器能正常启动 | ✅ PASS |
| 2 | 工具总数 = 62 | ✅ PASS（62） |
| 3 | Phase 1 八工具全部可用 | ✅ PASS |
| 4 | 销售公式 6 工具全部可用 | ✅ PASS |
| 5 | `fetch_keys` 未被暴露 | ✅ PASS |
| 6 | 中文内容不乱码 | ✅ PASS |
| 7 | MCP 测试全部通过 | ✅ PASS（10/10） |
| 8 | 现有测试无回归 | ✅ PASS |
| 9 | guide 工具 11 主题可调用 | ✅ PASS |
| 10 | 无恋爱场景表述 | ✅ PASS |

---

## 九、工具分类统计

| 类别 | 数量 | 定位 |
|------|------|------|
| 只读工具（含 Wiki 检索 3 个 + guide 1 个 + 工作流 2 个 + 配置 1 个） | 28 | **Wiki 工具是推理主轴，优先调用** |
| 写入工具（含 WCD/WeFlow 启动 + 配置 1 个） | 19 | 事实档案 + 分析归档 + 后端启动 |
| 公式工具（辅助参考） | 15 | chat-skills 遗产，核验而非套用 |
| **总计** | **62** | — |

> Wiki 工具：`wiki_context`（主入口）、`wiki_search`、`wiki_read`。Agent 分析前先检索 Wiki 找方法论，公式仅作辅助核验。
> guide 工具：11 个主题的操作指南，Agent 不确定流程时调用 `guide(topic)`。

---

## 十、Skill-MCP 融合架构

### 10.1 设计理念

本系统采用"**Skill 编排流程 + MCP 执行能力**"的融合架构，解决纯 MCP 缺乏业务流程指导、纯 Skill 缺乏标准化工具接口的问题。

| 层级 | 职责 | 实现 |
|------|------|------|
| **Skill 层** | 业务流程编排、决策规则定义、方法论框架 | `skill/` 下的 Markdown 文件 |
| **MCP 层** | 标准化数据接口、工具执行、安全隔离 | `mcp_server/` 下的 Python 工具 |
| **双向导航** | 工具与文档的双向索引、工作流指引 | `skill_map()` / `workflow_step()` |

### 10.2 核心工具

| 工具 | 功能 | 参数 |
|------|------|------|
| `skill_map(tool_name)` | 查询工具与 Skill 的双向映射，返回下一步建议 | `tool_name`: 工具名（可选，不传返回全部） |
| `workflow_step(workflow, step)` | 按步骤执行工作流，返回当前步骤详情和下一步指引 | `workflow`: 工作流名, `step`: 步骤编号（可选） |

### 10.3 工作流定义

| 工作流 | 名称 | 步骤数 | 适用场景 |
|--------|------|--------|----------|
| `analysis` | 客户分析完整流程 | 12 步 | "分析XX"、"帮我看看XX" |
| `emergency_reply` | 紧急回复流程 | 4 步 | "客户发了XX怎么回" |
| `weekly` | 周报流程 | 2 步 | "做周报" |
| `maintain` | 维持关系流程 | 4 步 | "维持关系" |

### 10.4 分析工作流（analysis）详细步骤

```
0: person_sync        → 同步最新消息
1: person_brief       → 获取全局视图
2: wiki_context       → 批量构建 Wiki 知识上下文（合并搜索+读取）
3: person_chat        → 获取聊天记录
4: person_metrics     → 获取指标数据
5: person_signals     → 获取信号详情
6: person_timeline    → 获取关系时间线
7: person_evidence    → 查阅事实档案
8: formula_get_params → 获取战态公式参数
9: sales_get_params  → 获取销售公式参数
10: sales_calc_bq     → 公式核验（辅助参考）
11: save_from_markdown → 保存分析报告
```

### 10.5 双向索引数据源

`skill/mcp_index.yaml` 是融合架构的核心数据源，包含：

- **tools**：58 个工具的映射（下一步建议、Skill 参考、工作流位置）
- **workflows**：4 个工作流的详细步骤定义
- **scenarios**：场景到工作流的路由映射

### 10.6 使用模式

**模式 1：按工作流执行（推荐）**

```python
workflow_step('analysis')        # 查看流程概览
workflow_step('analysis', 0)     # 获取第0步详情
person_sync('XX')                # 执行第0步
workflow_step('analysis', 1)     # 获取第1步详情
person_brief('XX')               # 执行第1步
# ...
```

**模式 2：工具驱动探索**

```python
skill_map('person_brief')        # 查 person_brief 之后能调什么
# 根据返回的下一步建议选择工具
```

**模式 3：场景路由**

```python
# 用户说"分析XX" → 路由到 analysis 工作流
# 用户说"客户发了XX怎么回" → 路由到 emergency_reply 工作流
```

### 10.7 工具描述增强

所有核心工具的 description 中嵌入了下一步建议：

| 工具 | 下一步建议 |
|------|-----------|
| `person_sync` | 调 `person_brief` 获取全局视图 |
| `person_brief` | 看到信号后立即调 `wiki_context` 建立方法论框架 |
| `person_chat` | 看到聊天模式后调 `wiki_context` |
| `person_metrics` | 看到数值后调 `wiki_context` 或 `sales_calc_bq` |
| `wiki_context` | 批量建框架后，如需精确单页钻取调 `wiki_search` + `wiki_read` |
| `wiki_search` | 找到条目后用 `wiki_read` 读全文 |
| `sales_get_params` | 接下来代入销售公式计算 |
