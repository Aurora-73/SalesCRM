# **长期规划，现在不做**

下面给你一份**可以直接落地的“工业级 Tool / API / Persistence 规范”**，目标是：

> 让 SalesCRM 从“脚本型 agent 工具集”升级为“可被 Web / Agent / MCP / CLI 统一调用的服务层”。

我会按**四层架构 + tools.py规范 + 数据契约 + 审计系统**一次性收敛。

---

# 一、总体架构（统一抽象）

你现在系统建议收敛为：

```text
┌──────────────────────────────┐
│        Client Layer           │
│  Web / Claude Code / MCP     │
└────────────┬─────────────────┘
             ↓
┌──────────────────────────────┐
│        API Layer              │
│  FastAPI / RPC / MCP Adapter │
└────────────┬─────────────────┘
             ↓
┌──────────────────────────────┐
│        Tool Layer             │
│   engine/tools.py (Agent API)│
└────────────┬─────────────────┘
             ↓
┌──────────────────────────────┐
│     Service Layer             │
│  analyzers / importers       │
│  metrics / wiki / memory     │
└────────────┬─────────────────┘
             ↓
┌──────────────────────────────┐
│      Data Layer               │
│ SQLite / Markdown / facts    │
└──────────────────────────────┘
```

---

# 二、核心设计原则（必须遵守）

## 1. Tool ≠ Report（关键原则）

| 类型   | 定义                             |
| ------ | -------------------------------- |
| Tool   | 原子能力（query / get / write）  |
| Report | tool组合后的结果（brief / rank） |

---

## 2. Tool 必须满足 4 个属性

```text
Deterministic
Stateless（除了写入类）
Typed I/O
Audit-able
```

---

## 3. 所有写操作必须可追踪

必须统一：

```text
actor / timestamp / trace_id
```

---

# 三、tools.py 工业级分层规范

---

# 3.1 Tool 分层结构

```python
engine/tools.py
```

拆为 5 类：

---

## ① READ_TOOLS（只读原子查询）

```python
query_messages()
query_contacts()
query_events()
query_metrics()
query_fact_archive()
query_analysis_history()
query_wiki()
```

特点：

* 返回“结构化数据”
* 不返回 opinion
* 不做 summary（交给 Agent）

---

## ② AGGREGATION_TOOLS（组合视图）

```python
get_brief()
get_rank()
get_timeline()
get_customer_snapshot()
```

特点：

* 允许轻度聚合
* 但禁止决策逻辑
* 只是“view layer”

---

## ③ WRITE_TOOLS（状态变更）

```python
save_note()
save_evaluation()
save_analysis()
save_event()
sync_data()
```

必须统一 schema：

```python
{
  "actor": "agent",
  "trace_id": "uuid",
  "timestamp": "...",
  "payload": {...}
}
```

---

## ④ DECISION_TOOLS（公式层）

```python
calc_bq()
calc_bsp()
calc_bws()
calc_pv()
calc_action()
```

原则：

* ❌ 不访问数据库
* ✔ 只接收输入参数
* ✔ 完全可复现

---

## ⑤ META_TOOLS（系统能力）

```python
health_check()
get_schema()
get_capabilities()
log_trace()
```

---

# 四、标准 Tool 返回结构（统一）

## 4.1 基础返回格式

```python
class ToolResponse:
    status: Literal["ok", "error"]
    data: Any
    meta: dict
```

---

## 4.2 meta 必须包含

```python
meta = {
    "tool": "query_messages",
    "trace_id": "uuid",
    "timestamp": "...",
    "latency_ms": 12,
    "source": ["sqlite", "fact_archive"],
}
```

---

## 4.3 error 格式统一

```python
{
  "status": "error",
  "error": {
    "code": "NOT_FOUND",
    "message": "...",
    "trace_id": "..."
  }
}
```

---

# 五、数据读写权限模型（关键）

## 5.1 权限分层

```text
Agent (Claude Code)
   ↓
Tool Layer
   ↓
Service Layer
   ↓
Data Layer
```

---

## 5.2 权限规则

| 操作           | 是否允许                |
| -------------- | ----------------------- |
| read_messages  | ✔                      |
| write_note     | ✔                      |
| write_analysis | ✔                      |
| delete_data    | ❌（禁止）              |
| raw_sql        | ❌（禁止Agent直接访问） |

---

## 5.3 强制约束

```text
Agent cannot directly access DB
Agent can only call tools
Tools enforce validation
```

---

# 六、审计系统（必须补）

这是你现在系统缺失的关键能力。

---

## 6.1 Audit Log Schema

```python
{
  "trace_id": "...",
  "actor": "agent",
  "tool": "save_analysis",
  "input": {...},
  "output": {...},
  "timestamp": "...",
  "latency_ms": 32
}
```

---

## 6.2 存储位置

```text
data/audit/YYYY-MM-DD.log
```

---

## 6.3 必须记录的事件

* tool call
* write operation
* sync operation
* analysis save

---

# 七、Agent 视角优化（非常关键）

你现在最大的问题不是 tool，而是：

> Agent 没有结构化认知输入

---

## 7.1 brief 必须分层输出

```text
## FACTS
- timeline
- contacts
- events

## METRICS
- bq / bsp / bws

## HISTORY
- previous analysis

## SIGNALS
- detected patterns
```

---

## 7.2 禁止：

❌ “一段长文本brief”

---

# 八、Persistence Layer（你当前最关键缺口）

## 8.1 必须新增统一存储结构

```text
data/memory/
  observations/
  hypotheses/
  decisions/
  analyses/
```

---

## 8.2 analysis 标准格式

```yaml
id: xxx
person: [REDACTED]
stage: 冷淡/停滞
confidence: 0.82

diagnosis: ...
strategy: ...
risks: ...

signals:
  - msg_drop
  - response_delay

trace:
  tool_calls:
    - query_messages
    - calc_bq
```

---

## 8.3 核心原则

> Analysis = 可追溯推理链，而不是文本

---

# 九、API Layer（为 Web / MCP 预留）

建议直接定义：

---

## 9.1 REST API

```text
GET  /person/{id}/brief
GET  /person/{id}/messages
GET  /person/{id}/metrics
GET  /person/{id}/analysis

POST /analysis/save
POST /note/save
POST /sync/run
```

---

## 9.2 Web / Agent 共用同一层

```text
Claude Code → tools.py → API service → DB
Web UI      → API service → DB
```

---

# 十、最终系统形态（收敛版）

你最终应该收敛为：

```text
               ┌────────────┐
               │   Agent    │
               └─────┬──────┘
                     ↓
            ┌───────────────┐
            │  tools layer   │
            └─────┬─────────┘
                  ↓
      ┌────────────────────────┐
      │ service + API layer    │
      └─────────┬──────────────┘
                ↓
        ┌───────────────┐
        │ data + memory  │
        └───────────────┘
```

---

# 十一、最重要的设计结论（帮你收敛思考）

你现在系统真正的“正确方向”只有三条：

---

## 1. Tool 变薄，不变多

* ❌ 不要拆成 50 个 getter
* ✔ 保持 query + filter

---

## 2. analysis 必须结构化 + 可回溯

这是系统“进化能力”的来源

---

## 3. Agent 不负责数据结构，只负责推理

所有复杂性必须在：

```text
tools + service layer
```

---

# 如果你下一步要继续，我可以帮你做三件更关键的事：

1. **直接帮你重写 tools.py（工业版实现）**
2. **设计 analysis + memory schema（可学习系统）**
3. **或者帮你把这个系统直接升级成 MCP server 架构**

你现在已经在“工具型 Agent 系统”的中后期了，不是早期demo阶段了。