# SalesCRM MCP 服务器

> **版本**：v1.0
> **工具数**：53 个（23 只读 + 15 写入 + 15 公式）
> **传输方式**：stdio
> **框架**：FastMCP 3.x

## 快速开始

### 1. 安装依赖

```bash
cd E:/Code/SalesCRM
pip install -r requirements.txt
```

### 2. 配置 MCP 客户端

在 Claude Desktop / Cursor / Windsurf 的 MCP 配置中添加：

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

配置文件已预置在 `.mcp.json`。

### 3. 启动

MCP 客户端会自动启动服务器。手动测试：

```bash
python -m mcp_server.server
```

### 4. 运行测试

```bash
python -X utf8 -m pytest mcp_server/tests/ -v
```

## 工具分类

### 只读工具（23 个）

| 工具 | 说明 |
|------|------|
| `person_brief` | 客户简要信息（身份、指标、事件、信号、最近消息） |
| `person_chat` | 聊天记录（按日期分组） |
| `person_metrics` | 详细关系指标 |
| `person_rank` | 所有客户商务热度排名 |
| `person_status` | 状态概览（精简版指标） |
| `wiki_search` | 搜索 Wiki 知识库 |
| `wiki_read` | 读取 Wiki 页面完整正文 |
| `person_timeline` | 客户关系时间线 |
| `person_signals` | 信号详情（基础+操控+朋友圈） |
| `person_evidence` | 事实档案 |
| `skill_search` | 搜索技能包 |
| `person_compare` | 对比历史分析变化 |
| `weekly_report` | 周报 |
| `person_moments_stats` | 朋友圈互动统计 |
| `maintain_list` | 需维持关系候选人列表 |
| `events_scan` | 扫描关系事件（只读） |
| `wcd_status` | WCD 后端状态检查 |
| `contact_search` | 搜索联系人 |
| `sticker_scan` | 扫描贴纸表情 |
| `sticker_list` | 列出贴纸词典 |
| `exclude_list` | 查看排除列表 |
| `failure_list` | 查看失败案例 |
| `message_context` | 消息上下文查询 |

### 写入工具（15 个）

| 工具 | 说明 | 风险等级 |
|------|------|---------|
| `person_note` | 添加客户备注 | 追加 |
| `person_date_record` | 记录会面信息 | 追加 |
| `person_sync` | 增量同步单客户消息 | 同步 |
| `person_save_analysis` | 保存分析结论 | 覆盖 |
| `events_save` | 写入关系事件 | 追加 |
| `person_evaluate` | 添加客户评价 | 追加 |
| `system_sync` | 全量/增量数据同步 | 同步 |
| `contact_alias` | 添加联系人别名 | 追加 |
| `contact_merge` | 合并联系人 | ⚠️ 不可逆 |
| `sticker_label` | 标注贴纸含义 | 追加 |
| `exclude_add` | 加入排除列表 | 修改 |
| `exclude_remove` | 移出排除列表 | 修改 |
| `failure_add` | 记录失败案例 | 追加 |
| `save_from_markdown` | 从 Markdown 保存分析 | 覆盖 |
| `sync_moments` | 同步朋友圈互动 | 追加 |

### 公式工具（15 个）

**战态分析公式（9 个）：**

| 工具 | 说明 |
|------|------|
| `formula_get_params` | 获取公式参数（自动计算） |
| `formula_calc_ivi` | IVI — 意图真实度 |
| `formula_calc_spe` | SPE — 社交势能 |
| `formula_calc_ews` | EWS — 推进窗口期 |
| `formula_calc_is` | IS — 真实合作度 |
| `formula_calc_gap_effect` | Gap_Effect — 情绪落差刺激 |
| `formula_calc_eev` | EEV — 推进期望值 |
| `formula_calc_cs` | CS — 矛盾演化状态 |
| `formula_calc_action` | 行动决策（推进/拉扯/重置/维持） |

**销售决策公式（6 个，SalesCRM 独有）：**

| 工具 | 说明 |
|------|------|
| `sales_get_params` | 获取销售公式参数（自动计算） |
| `sales_calc_bq` | BQ — 购买意愿真实度 |
| `sales_calc_bsp` | BSP — 商务势能 |
| `sales_calc_bws` | BWS — 购买意向期 |
| `sales_calc_pv` | PV — 成交期望值 |
| `sales_calc_action` | 销售行动决策（bargain/push/nurture/reset/maintain） |

## 安全设计

- **fetch_keys 永不暴露**：会重启微信并要求扫码，AI 无法完成
- **wcd_status 只读**：只检查状态，不自动获取密钥
- **contact_merge 不可逆**：内置同人检查（source == target 时拒绝执行）
- **参数校验**：所有公式参数 clamp 到 [0,1] 范围，超出自动截断并标注

## 架构

```
Claude Desktop / Cursor / Windsurf
        │ (MCP stdio)
        ▼
┌───────────────┐
│  MCP Server   │  mcp_server/server.py
│  (FastMCP)    │
└───────┬───────┘
        │ Python 函数调用
        ▼
┌───────────────┐
│ engine/tools.py │  复用现有工具层
└───────┬───────┘
        ▼
engine/analyzers/ + engine/agent/ + engine/knowledge/
```

## 文件结构

```
mcp_server/
├── __init__.py          # 包标识
├── server.py            # FastMCP 入口，注册 53 个工具
├── tools_read.py        # 23 个只读工具
├── tools_write.py       # 15 个写入工具
├── tools_formula.py     # 15 个公式工具（9 战态 + 6 销售）
├── README.md            # 本文件
├── QUALITY_CHECK.md     # 质量自检报告
├── TOOL_MAPPING.md      # 工具映射表
├── ISSUES.md            # 问题记录
└── tests/
    ├── __init__.py
    ├── conftest.py      # tools fixture
    └── test_final.py    # 全量验收测试
```
