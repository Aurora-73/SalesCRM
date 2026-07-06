<p align="center">
  <img src="架构图.png" alt="SalesCRM 架构图" width="720">
</p>

<h1 align="center">SalesCRM</h1>

<p align="center">
  <em>AI 驱动的本地微信销售客户分析助手</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/MCP-55%20tools-green?logo=claude" alt="MCP Tools">
  <img src="https://img.shields.io/badge/license-MIT-yellow" alt="License">
</p>

<p align="center">
  <b>代码负责数据，Agent 负责推理。</b>
</p>

---

## 简介

SalesCRM 是一个**本地优先**的 AI 销售客户分析工具。它从微信聊天记录中自动同步客户沟通数据，通过指标体系量化客户意向，结合销售知识库和 Agent 推理生成跟进建议。

**解决的问题：** 销售每天在微信上跟大量客户沟通，进度记不住、优先级理不清、信号看不全。SalesCRM 让 AI 替你完成这些重复分析工作。

**不做什么：** 不是群发工具、不是公司级 CRM 替代品、不需要手动填数据。

---

## 工作流

```
微信聊天 ──→  同步管道  ──→  指标/事件/排名  ──→  事实档案  ──→  Agent 推理
(WCD/WeFlow)   (importers)    (analyzers)       (customers/)   ① Wiki 方法论
                                    ↑                          ② 查档案
                                    └── 公式辅助参考 ──────────  ③ 看数据
                                      (IVI/SPE/BQ/BSP…)        ④ 核验公式
```

---

## 功能特性

- **数据自动同步** — 从微信自动拉取联系人、消息、朋友圈，无需手动录入。支持 WCD（解密微信数据库）和 WeFlow（HTTP API）两种后端。
- **客户身份目录** — Person → Account → Alias 三层映射。一个客户可绑定多个微信号和昵称，任意别名模糊搜索都能定位。
- **15 维量化指标** — 回复率、回复速度、情绪质量、朋友圈互动、活跃趋势等，输出客户意向等级和互动模式。
- **事件检测** — 自动识别首次聊天、断联、恢复联系、需求确认、决策人出现、方案发送等关键销售节点。
- **辅助参考公式** — 通用战态（IVI/SPE/EWS）和销售专属（BQ/BSP/BWS/PV）公式，为 Agent 推理提供量化视角。
- **知识库驱动** — 内置 OKF 格式销售知识库（Wiki），Agent 以方法论为推理主轴，而非机械套用公式阈值。
- **MCP 服务器** — 55 个工具暴露给 Claude Desktop、Cursor 等 AI 客户端（23 只读 + 17 写入 + 15 公式），AI 可直接驱动分析。

---

## 快速开始

### 环境要求

- Python 3.10+
- 数据后端：WCD（[WeChatDataAnalysis](https://github.com/LC044/WeChatMsg)）或 WeFlow

### 安装与运行

```bash
# 1. 安装依赖
pip install pyyaml

# 2. 初始化数据库
python -c "from engine.importers.db_init import init_db; init_db()"

# 3. 编辑配置
# data/system/config.yaml 中设置后端类型、地址和 token

# 4. 同步微信数据
python -c "from engine.tools import sync; sync()"

# 5. 查看客户排名
python -c "from engine.tools import rank; print(rank())"

# 6.（可选）启动 MCP 服务器接入 AI 客户端
python -m mcp_server.server
```

---

## 架构设计

### 核心原则

**代码负责数据，Agent 负责推理。** 系统提供完整的数-据采集、指标计算、事实存储管线，而分析和决策全部交给 AI Agent 完成。

### 数据流

```
微信客户端
    ↓ WCD / WeFlow API
importers/ (同步管道: 消息/联系人/朋友圈)
    ↓
core.db (SQLite 本地数据库)
    ↓
analyzers/ (15 维指标计算 + 事件检测 + 排名)
    ↓
Agent 工具层 (tools.py) → Agent 推理循环
    ├─ ① 读 Wiki 找方法论框架
    ├─ ② 查事实档案了解历史
    ├─ ③ 看实时聊天和指标数据
    └─ ④ 核验公式获取量化参考
```

### 身份目录

```
Person (自然人) → Account (微信号) → Alias (昵称/备注/别名)
```

支持模糊搜索任意别名找到对应客户，一个客户绑定多个微信账号。

### 两种数据后端

| 后端 | 原理 | 适用场景 |
|------|------|---------|
| **WCD** | 解密微信本地数据库直接读取 | 数据完整、支持朋友圈，需解密环境 |
| **WeFlow** | HTTP API 拉取 | 轻量部署、跨平台，功能相对受限 |

---

## 对比

| 维度 | SalesCRM | 传统 CRM | WeTool/微伴 |
|------|----------|----------|-------------|
| 数据来源 | 微信自动同步 | 手动录入 | 微信群发 |
| 意向量化 | 公式 + 知识库推理 | 销售自己填 | 无 |
| 销售方法论 | 内置 Wiki 知识库 | 无 | 无 |
| 数据安全 | 全本地 | 上云 | 上云 |
| 部署成本 | 本地搭环境 | 付费订阅 | 付费 |

---

## 项目结构

```
SalesCRM/
├── engine/               # 核心引擎
│   ├── tools.py          # 工具函数统一入口
│   ├── config.py         # 配置管理
│   ├── formulas.py       # 战态公式 (IVI/SPE/EWS)
│   ├── formulas_sales.py # 销售公式 (BQ/BSP/BWS/PV)
│   ├── agent/            # Agent 工具实现
│   ├── analyzers/        # 指标、排名、事件、周报
│   ├── identity/         # 身份目录 (Person/Account/Alias)
│   ├── importers/        # 数据同步管道
│   ├── facts/            # 事实档案
│   └── knowledge/        # Wiki 知识库检索
├── mcp_server/           # MCP 服务器 (55 个工具)
├── docs/wiki/            # 销售知识库 (OKF 格式, 独立仓库)
├── readme/               # 模块文档
├── tests/                # 测试
├── data/                 # 本地数据 (.gitignored)
└── 架构图.png            # 架构示意图
```

---

## 文档

| 文档 | 说明 |
|------|------|
| [PROJECT.md](readme/PROJECT.md) | 项目总览与功能清单 |
| [agent.md](readme/agent.md) | Agent 工具层实现 |
| [analyzers.md](readme/analyzers.md) | 指标引擎与排名算法 |
| [identity.md](readme/identity.md) | 身份目录三层映射 |
| [facts.md](readme/facts.md) | 事实档案结构 |
| [importers.md](readme/importers.md) | 数据同步管道 |
| [formulas.md](readme/formulas.md) | 辅助参考公式体系 |
| [knowledge.md](readme/knowledge.md) | Wiki 知识库 |
| [mcp.md](readme/mcp.md) | MCP 服务器工具清单 |
| [models.md](readme/models.md) | 数据模型定义 |
| [tools.md](readme/tools.md) | 工具函数速查表 |

---

## License

[MIT](LICENSE)
