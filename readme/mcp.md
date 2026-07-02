# SalesCRM MCP 服务器

> **状态**：已完工 — 55 个工具全部注册，全量验收通过
> **最后更新**：2026-07-02

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
├── server.py                # FastMCP 入口，注册 55 个工具
├── tools_read.py            # 只读工具（23 个）+ wcd_start（写入）
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

## 五、工具清单（55 个）

> **Wiki 工具优先**：`wiki_search` 是 Agent 推理的第一依据，分析前先检索 Wiki 找方法论框架。
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

### 5.2 Phase 2 P0 — 即时补齐（3 个）

`wiki_read`（只读，**Wiki 全文读取，Agent 推理主轴**）、`person_sync`（写入）、`person_save_analysis`（写入）

### 5.3 Phase 2 P1 — 已实现工具（13 个）

**只读（8 个）：** `person_timeline`、`person_signals`、`person_evidence`、`skill_search`、`person_compare`、`weekly_report`、`person_moments_stats`、`maintain_list`、`events_scan`、`wcd_status`

**写入（4 个）：** `events_save`、`person_evaluate`、`system_sync`、`wcd_start`（启动 WCD 后端进程）

### 5.4 Phase 2 P2 — 拆分工具（14 个）

**只读（6 个）：** `contact_search`、`sticker_scan`、`sticker_list`、`exclude_list`、`failure_list`、`message_context`

**写入（8 个）：** `contact_alias`、`contact_merge`（不可逆）、`sticker_label`、`exclude_add`、`exclude_remove`、`failure_add`、`save_from_markdown`、`sync_moments`

### 5.5 Phase 3 P3 — 公式工具（15 个，辅助参考）

> **定位**：公式是 chat-skills 遗产的辅助参考视角，Agent 核验而非套用。阈值非硬规则，最终决策由 Agent 基于 Wiki + 事实档案 + 实时数据综合判断。详见 `readme/formulas.md`。

**通用战态公式（9 个，辅助参考）：** `formula_get_params`、`formula_calc_ivi`（Wiki 依据：`[[购买意向指标]]`）、`formula_calc_spe`（`[[框架]]`）、`formula_calc_ews`（`[[窗口识别]]`）、`formula_calc_is`、`formula_calc_gap_effect`（`[[情绪落差（GapEffect）]]`）、`formula_calc_eev`、`formula_calc_cs`、`formula_calc_action`

**销售专属公式（6 个，辅助参考，SalesCRM 独有）：** `sales_get_params`、`sales_calc_bq`（`[[购买意向指标]]`）、`sales_calc_bsp`（`[[框架]]`）、`sales_calc_bws`（`[[窗口识别]]`）、`sales_calc_pv`、`sales_calc_action`

### 5.6 使用指南工具（1 个）

| 工具名 | 参数 | 说明 | 类型 |
|--------|------|------|------|
| `guide` | `topic` | 获取使用指南和工作流文档。11 个主题：getting-started / workflow/analysis / report-template / methodology / rules/evidence / rules/permissions / rules/reply / workflow/maintain / reference/sync / reference/formula / reference/stickers。支持中文别名 | 只读 |

### 5.7 永不暴露

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
| 2 | 工具总数 = 55 | ✅ PASS（55） |
| 3 | Phase 1 八工具全部可用 | ✅ PASS |
| 4 | 销售公式 6 工具全部可用 | ✅ PASS |
| 5 | `fetch_keys` 未被暴露 | ✅ PASS |
| 6 | 中文内容不乱码 | ✅ PASS |
| 7 | MCP 测试全部通过 | ✅ PASS（10/10） |
| 8 | 现有测试无回归 | ✅ PASS |
| 9 | guide 工具 11 主题可调用 | ✅ PASS |
| 10 | 无 loveMentor / 恋爱表述 | ✅ PASS |

---

## 九、工具分类统计

| 类别 | 数量 | 定位 |
|------|------|------|
| 只读工具（含 Wiki 检索 3 个 + guide 1 个） | 24 | **Wiki 工具是推理主轴，优先调用** |
| 写入工具 | 16 | 事实档案 + 分析归档 + WCD 启动 |
| 公式工具（辅助参考） | 15 | chat-skills 遗产，核验而非套用 |
| **总计** | **55** | — |

> Wiki 工具：`wiki_search`、`wiki_read`、`skill_search`。Agent 分析前先检索 Wiki 找方法论，公式仅作辅助核验。
> guide 工具：11 个主题的操作指南，Agent 不确定流程时调用 `guide(topic)`。
