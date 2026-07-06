# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Agent 行为规范。详细架构和工具文档见 `readme/PROJECT.md` 和 `readme/` 下的模块文档。

## 核心原则

代码负责数据，Agent 负责推理。

## 项目概述

AI 驱动的本地销售客户分析助手。从微信聊天记录自动同步 → 计算客户指标 → 识别销售时机 → Agent 推理决策。

## 常用命令

```bash
# 运行全部测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_formulas.py -v

# 运行单个测试用例
python -m pytest tests/test_formulas.py::test_ivi_calculation -v

# MCP 服务器测试
python -m pytest mcp_server/tests/ -v

# 同步微信数据
python -c "from engine.tools import sync; sync()"

# 同步单个客户最新消息（分析前必做）
python -c "from engine.tools import sync_person; sync_person('客户名')"

# 启动 MCP 服务器（stdio 模式，供 Claude Desktop 等使用）
python -m mcp_server.server

# 查看客户状态
python -c "from engine.tools import brief; print(brief('客户名'))"

# 查看客户聊天记录
python -c "from engine.tools import chat; print(chat('客户名', recent=50))"

# 生成周报
python -c "from engine.tools import weekly; print(weekly())"

# 初始化数据库
python -c "from engine.importers.db_init import init_db; init_db()"

# 查看所有客户排名
python -c "from engine.tools import rank; print(rank())"
```

## 目录结构

```
SalesCRM/
├── engine/                  # 核心引擎
│   ├── tools.py             # Agent 工具统一入口（所有数据操作必经之路）
│   ├── config.py            # 配置管理 + 路径常量
│   ├── formulas.py          # 辅助参考公式（通用战态 IVI/SPE/EWS）
│   ├── formulas_sales.py    # 销售专属公式（BQ/BSP/BWS/PV）
│   ├── formulas_love.py     # 情感战态公式
│   ├── stickers.py          # 贴纸管理
│   ├── agent/               # Agent 工具实现层（每个域一个模块）
│   │   ├── core.py          # 共享基础设施（_get_conn、_resolve_person）
│   │   ├── brief.py         # 全局摘要视图
│   │   ├── chat.py          # 聊天记录查询
│   │   ├── evidence.py      # 事实档案视图
│   │   ├── write.py         # 数据写入（note/date/evaluate/events/analysis）
│   │   ├── report.py        # 指标/排名/周报
│   │   ├── signals.py       # 信号检测
│   │   ├── sync_agent.py    # 数据同步入口
│   │   ├── identity_ops.py  # 身份/排除/失败案例管理
│   │   ├── material.py      # 知识材料搜索
│   │   ├── maintain.py      # 客户维护推荐
│   │   └── context.py       # 上下文组装
│   ├── analyzers/           # 分析引擎
│   │   ├── metrics.py       # 15 维客户指标
│   │   ├── ranker.py        # 客户排序
│   │   ├── events.py        # 事件检测
│   │   └── weekly_report.py # 周报生成
│   ├── identity/            # 身份目录（Person→Account→Alias 三级映射）
│   │   └── directory.py     # 身份解析全部实现
│   ├── facts/               # 事实档案（people_archive, failure_archive）
│   ├── importers/           # 数据同步管道
│   │   ├── sync.py          # 同步调度
│   │   ├── wcd_client.py    # WCD 后端客户端
│   │   ├── weflow_client.py # WeFlow 后端客户端
│   │   └── db_init.py       # 数据库初始化
│   └── knowledge/           # Wiki 知识库检索
│       └── wiki_retriever.py
├── mcp_server/              # MCP 服务器（53 个工具）
│   ├── server.py            # FastMCP 服务器入口
│   ├── tools_read.py        # 只读工具注册
│   ├── tools_write.py       # 写入工具注册
│   ├── tools_formula.py     # 公式工具注册
│   └── tests/               # MCP 集成测试
├── docs/wiki/               # OKF 销售知识库（推理主轴）
├── tests/                   # 引擎测试
│   ├── conftest.py          # 共享 fixture（tmp_db, test_config, insert_messages 等）
│   ├── test_formulas.py     # 公式测试
│   ├── test_identity.py     # 身份目录测试
│   ├── test_metrics.py      # 指标测试
│   └── ...
├── readme/                  # 模块文档
├── data/                    # 本地数据（.gitignored）
│   ├── raw/core.db          # SQLite 主数据库
│   ├── customers/           # 事实档案（每人一个子目录）
│   ├── system/config.yaml   # 系统配置
│   └── outputs/             # 输出（排名、报告、分析）
└── exchange/                # 跨项目同步（Windows Junction）
```

## 数据流

```
微信聊天 → importers/ 同步管道 → data/raw/core.db (SQLite)
  → analyzers/ 计算指标/事件/排名
  → agent/ 工具函数（通过 tools.py 统一入口）
  → Agent 推理（读 Wiki → 查档案 → 看数据 → 核验公式）
```

## 工具入口

所有数据操作通过 `engine/tools.py`：

```python
from engine.tools import brief, metrics, chat, wiki_search, rank, status
from engine.tools import brief_data, chat_data, message_context_data
from engine.tools import note, date, evaluate, events, save_analysis
from engine.tools import contact, exclude, failure, sticker
from engine.tools import sync, sync_person, weekly
```

函数签名统一规则：第一个参数是 `name: str`（人名），内部自动解析数据库连接和身份。详见 `readme/tools.md`。

## 核心架构模式

### 三层映射（身份目录）
`Person`（自然人）→ `Account`（微信号）→ `Alias`（别名/昵称）。模糊搜索任意别名都能找到对应客户。

### 指标引擎
`engine/analyzers/metrics.py` 计算 15 维指标（回复率、速度、情绪质量、朋友圈互动、活跃趋势等），`ranker.py` 综合排序。

### Wiki 知识库（推理主轴）
`docs/wiki/` 下的 OKF 格式销售知识，通过 `wiki_retriever.py` 检索。Agent 分析时以 Wiki 方法论为推理主轴。

### 辅助公式
通用战态（IVI/SPE/EWS）和销售专属（BQ/BSP/BWS/PV）公式在 `formulas.py` 和 `formulas_sales.py` 中。公式是辅助参考，Agent 核验而非机械套用。

### 两种后端
WCD（WeChatDataAnalysis，解密微信数据库）和 WeFlow（HTTP API），通过 `config.yaml` 的 `weflow.backend` 切换。同步管道接口兼容。

## 数据层优先级

Agent 分析顺序：① 读 Wiki 找方法论 → ② 查事实档案 → ③ 看实时数据 → ④ 核验公式

冲突裁决（数据矛盾时）：实时数据 > 事实档案 > Wiki 知识库 > 事件检测 > 公式计算 > 历史分析

## 权限规范

| 操作类型 | 工具 | Agent 行为要求 |
|---------|------|--------------|
| 只读 | brief/chat/evidence/metrics/status/rank/wiki_*/formula_*/sales_* | 自由调用 |
| 追加写入 | note/date_record/evaluate | 直接执行，无需确认 |
| 覆盖写入 | save_analysis/save_from_markdown | 覆盖前告知用户 |
| 检测写入 | events_save | 建议先 scan 展示结果再写入 |
| 不可逆操作 | contact_merge | **必须向用户确认后再执行** |

## 禁止事项

- **禁止直接用 `sqlite3` 查数据库**：所有数据操作必须通过 `engine/tools.py`
- **禁止自己写 SQL**：工具函数已封装所有查询
- **禁止导出原始数据库记录到文件**
- **禁止向 `data/input/` 写入任何文件**
- **禁止调用 LLM API**（Agent 自己就是 LLM）
- **禁止读取 `data/input/` 下的文件作为分析依据**：用 `chat()` 从数据库获取

## 同步规范

- `sync()` 只处理私聊（type='private'），`sync_person()` 不限
- 默认增量同步（`mode='incremental'`），全量（`mode='full'`）仅数据修复时用
- 同步前确保 WCD 后端已启动：`cd _reference/WeChatDataAnalysis && uv run main.py &`
- 同步管道用 `get_messages` API（可靠），不用 `pull_messages`（不可靠）

## 隐私规则

- 禁止在任何非 `.gitignore` 文件中写入真实联系人信息，用假名代替
- `data/raw/core.db`、`data/system/config.yaml`、`data/customers/` 均为私有本地数据，不得写入可提交文件

## 写入事实档案的自检三问

1. 是客户说的/做的，还是我推断的？→ 只能写前者
2. 换一个 Agent 读这条信息，会得出同样的结论吗？→ 如果不会，说明掺杂了判断
3. 这条信息 3 个月后还有效吗？→ 事实是稳定的，判断会过时

## 跨项目同步（Exchange）

每次完成代码修改后自检：这个改动在 lM 那边也能用吗？
- 通用改动（工具函数、Bug 修复、性能优化、测试补充）→ 写 exchange 记录
- 业务专属（销售术语、商机模型、话术模板）→ 不写 exchange

## Agent Skill

`.claude/skills/` 下 5 个渐进式披露文件（主入口 + 分析/工具/方法论/规则），详见 skill 文件。

## 环境

- Python 3.10+
- 外部依赖：`pyyaml`、`rapidocr-onnxruntime`、`Pillow`（同步管道和分析器使用 Python 标准库）
- 平台：Windows（主），macOS/Linux 兼容
- 数据后端：WCD（WeChatDataAnalysis）或 WeFlow
- MCP 框架：FastMCP 3.x（stdio 传输）
