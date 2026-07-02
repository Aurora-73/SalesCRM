# CLAUDE.md

Agent 行为规范。详细架构和工具文档见 `readme/PROJECT.md` 和 `readme/` 下的模块文档。

## 核心原则

代码负责数据，Agent 负责推理。

## 工具入口

所有数据操作通过 `engine/tools.py`：

```python
from engine.tools import brief, metrics, chat, wiki_search, rank, status
from engine.tools import brief_data, chat_data, message_context_data
from engine.tools import note, date, evaluate, events, save_analysis
from engine.tools import contact, exclude, failure, sticker
from engine.tools import sync, sync_person, weekly
```

详细签名见 `readme/tools.md` 工具速查表。

## 禁止事项

- **禁止直接用 `sqlite3` 查数据库**：所有数据操作必须通过 `engine/tools.py` 的函数。直接查库会绕过身份解析，导致 sender 标注混乱。
- **禁止自己写 SQL**：工具函数已封装所有查询，不要重复造轮子。
- **禁止导出原始数据库记录到文件**：会产生冗余文件，且原始 wxid 无法直接理解。
- **禁止向 `data/input/` 写入任何文件**：该目录仅用于用户手动放置截图，agent 不应写入。
- **禁止读取 `data/input/` 下的文件作为分析依据**：用 `chat()` 从数据库获取。
- **禁止调用 LLM API**：Agent 自己就是 LLM，不需要再调 Anthropic/OpenAI 等 API。

## 数据层优先级

Agent 分析时分两层理解：**操作顺序**（按什么顺序查）和**冲突裁决**（谁说了算）。

**操作顺序**：① 读 Wiki 找方法论 → ② 查事实档案 → ③ 看实时数据 → ④ 核验公式

**冲突裁决规则**（当数据矛盾时）：

| 优先级 | 数据来源 | 工具 | 性质 |
|--------|---------|------|------|
| 1（最高） | 实时数据 | brief/chat/metrics/status | 当前事实，不可推翻 |
| 2 | 事实档案 | evidence | 用户记录的客观事实 |
| 3 | OKF 知识库 | wiki_search/wiki_show | 方法论依据，推理主轴 |
| 4 | 事件检测 | events | 从数据推导的事件 |
| 5 | 公式计算 | sales_*/formula_* | 辅助参考视角，有启发但需核验 |
| 6（最低） | 历史分析 | data/outputs/analysis/ | 过去的观点，可能已过时 |

当实时数据与历史分析矛盾时，以实时数据为准。Wiki 是推理主轴提供解释框架，公式是辅助参考不主导决策。

## 权限规范

| 操作类型 | 工具 | Agent 行为要求 |
|---------|------|--------------|
| 只读 | brief/chat/evidence/metrics/status/rank/wiki_*/moments_stats/formula_*/sales_* | 自由调用 |
| 追加写入 | note/date/evaluate | 直接执行，无需确认 |
| 覆盖写入 | save_analysis/save_from_markdown | 覆盖前告知用户 |
| 检测写入 | events(scan=True) | 先展示检测结果，再写入 |
| 不可逆操作 | contact(merge) | **必须向用户确认后再执行** |

## Privacy Rules

- 禁止在任何非 `.gitignore` 文件中写入真实联系人信息。用假名代替。
- `data/raw/core.db`、`data/system/config.yaml`、`data/customers/` 均为私有本地数据，不得写入可提交文件。

## Agent Skill

`.claude/skills/sales-crm.md` — 统一入口 skill（决策树 + 工具速查 + 分析流程模板 + 指标体系）。

其他 skill：`person-info.md`（客户信息管理）、`chat-analyzer.md`（聊天深度分析）。

## 同步规范

- **自动解密**：`sync()` 和 `sync_person()` 使用 WCD 后端时，自动调用 `/api/decrypt` 刷新数据库快照（用缓存密钥，不重启微信），无需手动干预。
- **仅同步私聊**：`sync()` 只处理 `type='private'` 的会话（个人聊天），群聊和公众号消息不会被同步。`sync_person()` 不受此限制。
- **默认增量同步**：`sync()` 和 `sync_person()` 默认 `mode='incremental'`，日常使用增量模式。
- **少用全量**：`mode='full'` 仅在数据修复时使用。
- **WCD 启动**：同步前确保 WCD API 已启动：`cd _reference/WeChatDataAnalysis && uv run main.py &`
- **禁止频繁调用 `fetch_keys`**：此操作会重启微信并要求扫码登录。密钥通过 `account_keys.json` 持久化，WCD 启动时自动加载。
- **数据后端**：通过 `config.yaml` 的 `weflow.backend` 切换 `"wcd"` 或 `"weflow"`，两个客户端接口兼容。

## Conventions

- Wiki 和分析框架使用中文，技术术语保留英文。
- `engine/` 的外部依赖：`pyyaml`、`rapidocr-onnxruntime`、`Pillow`。同步管道和分析器使用 Python 标准库。
- **事实档案概念分层**（`data/customers/`）：
  - **evidence layer（事实层）**：`note` / `date` / `events` 写入的客观事实，高可信度
  - **evaluation layer（分析归档）**：`evaluate` / `save_analysis` 写入的主观判断，低优先级参考
  - 概念上分层，文件结构暂不重构
- **写入事实档案的自检三问**（写入前必答）：
  1. 这条信息是客户说的/做的，还是我推断的？→ 只能写前者
  2. 如果换一个 Agent 读这条信息，会得出同样的结论吗？→ 如果不会，说明掺杂了判断
  3. 这条信息 3 个月后还有效吗？→ 事实是稳定的，判断会过时
- 同步管道用 `get_messages` API（可靠），不用 `pull_messages`（不可靠）。

## 跨项目同步（Exchange）

阅读 exchange\README.md。每次完成代码修改后，**先做一次自检**：

> 这个改动在 lM 那边也能用吗？

| 情况 | 操作 |
|------|------|
| 通用改动（工具函数、Bug 修复、性能优化、测试补充） | **写一条 exchange 记录**到 `exchange/YYYY-MM-DD_描述.md` |
| 业务专属（销售术语、商机模型、话术模板） | 不写 exchange，各自维护 |
| 知识库 / 业务数据 | 不写 exchange，docs 和 data 是独立 git |

Exchange 目录通过 Windows Junction 在两个项目之间共享，写一边两边都能看到。
