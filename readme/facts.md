# 事实档案

## 概述

`engine/facts/` 管理 SalesCRM 的持久化事实层，包括客户事实档案和失败案例归档。事实层只记录客观事实，不负责销售判断、不生成策略，也不替代分析结论。

**原则**：事实归 facts，判断归 analysis。

| 类型 | 存储位置 | 内容 |
| --- | --- | --- |
| 客户事实档案 | `data/customers/*.md` | 客户基础信息、沟通时间线、备注、会面记录 |
| 自我档案 | `data/facts/self/*.md` | 本账号或销售本人相关事实 |
| 失败案例 | `data/facts/failures/*.yaml` | 失败商机、失败原因、复盘教训 |
| 分析结论 | `data/outputs/analysis/` | Agent 对客户状态和策略的主观判断 |

---

## 核心文件

| 文件 | 功能 |
| --- | --- |
| `people_archive.py` | 客户事实档案路径生成、迁移、初始化和追加写入 |
| `failure_archive.py` | 失败案例 YAML 读写和相似案例检索 |
| `__init__.py` | facts 包导出 |

---

## 客户事实档案

### 存储位置

```text
data/customers/
├── 张三__person_abcd1234.md
├── 李四__person_efgh5678.md
└── _TEMPLATE.md

data/facts/self/
└── 我__person_xxxx.md
```

文件名格式：

```text
<slug_display_name>__<person_id>.md
```

路径由 `get_person_archive_path(person, my_wxid=...)` 生成。如果客户身份对应 `config.my_wxid`，文件进入 `data/facts/self/`，否则进入 `data/customers/`。

### 当前文件结构

新档案由 `people_archive.py` 初始化为以下结构：

```markdown
---
person_id: person_abcd1234
display_name: 张三
updated_at: 2026-06-30T18:00:00
---

# 张三

> 创建日期：2026-06-30
> 最后更新：2026-06-30
> person_id：person_abcd1234
> wxid：wxid_xxx
> 微信昵称：客户昵称

## 基本信息

## 数据概览

## 关系时间线

## 当前状态

## 关键信息

## Dates

## Notes
```

说明：

- `## 关系时间线` 是历史字段名，在 SalesCRM 中表示客户沟通时间线或商机时间线。
- `## Dates` 不只表示线下见面，也可以记录电话、会议、演示、报价沟通等重要节点。
- `## Notes` 用于客观备注，例如预算、决策人、客户原话、产品偏好。
- 当前实现不会在每次写入时强制刷新 frontmatter 的 `updated_at`，它主要保证 frontmatter 存在。

---

## 写入函数

### append_note

```python
def append_note(person: IdentityPerson, text: str, *, my_wxid: str = "") -> Path:
    """添加备注到 ## Notes。"""
```

写入格式：

```markdown
- 2026-06-30 18:00 客户说预算审批需要老板确认
```

Agent 入口：

```python
from engine.tools import note
note("张三", "客户说预算审批需要老板确认")
```

适合记录：

- 客户公司、职位、行业、业务场景
- 预算、采购周期、决策人、竞品
- 客户明确说过的需求或限制
- 销售跟进中必须记住的客观信息

不适合记录：

- “客户很没诚意”这类主观判断
- “建议下周逼单”这类策略
- 没有证据的猜测

### append_event

```python
def append_event(
    person: IdentityPerson,
    event_date: str,
    event_type: str,
    detail: str,
    *,
    my_wxid: str = "",
) -> Path:
    """将事件写入 ## 关系时间线。"""
```

写入格式：

```markdown
- [2026-06-30] REQUIREMENT_CONFIRM: 客户确认需要销售分析工具
```

Agent 入口：

```python
from engine.tools import events
events("张三", scan=True)
```

常见事件：

| 事件 | 含义 |
| --- | --- |
| `FIRST_CHAT` | 首次聊天 |
| `DISCONNECT` | 断联 |
| `RECONNECT` | 恢复联系 |
| `FREQUENCY_UP` | 沟通频率上升 |
| `FREQUENCY_DOWN` | 沟通频率下降 |
| `REQUIREMENT_CONFIRM` | 需求确认 |
| `DECISION_MAKER_APPEAR` | 决策人出现 |
| `PROPOSAL_SENT` | 方案或报价发送 |

### append_date_entry

```python
def append_date_entry(
    person: IdentityPerson,
    *,
    date_text: str | None,
    location: str | None,
    rating: int | None,
    my_wxid: str = "",
) -> Path:
    """添加一次重要沟通记录到 ## Dates。"""
```

写入格式：

```markdown
### 2026-06-30
- 地点：线上演示；评分：4/5
```

Agent 入口：

```python
from engine.tools import date
date("张三", date_text="2026-06-30", location="线上演示", rating=4)
```

在 SalesCRM 中，`date()` 可用于记录：

- 线下面谈
- 电话会议
- 产品演示
- 方案讲解
- 报价沟通
- 复盘会议

### rename_person_archive

```python
def rename_person_archive(person: IdentityPerson, new_display_name: str, *, my_wxid: str = "") -> Path | None:
    """客户显示名变化时重命名档案文件。"""
```

通常由身份管理工具间接使用，避免手动改文件名导致路径与身份目录不一致。

---

## 读取和展示

Agent 不应直接解析 Markdown 文件，优先使用工具：

```python
from engine.tools import evidence, brief

evidence("张三")
evidence("张三", section="notes")
evidence("张三", section="timeline")
brief("张三", compact=True)
```

`evidence()` 会通过身份目录解析客户，再读取对应事实档案。这样可以兼容别名、多账号和自我档案路径。

---

## 失败案例归档

`failure_archive.py` 将失败案例保存为 YAML，位置：

```text
data/facts/failures/
├── 2026-06-30_张三.yaml
└── ...
```

核心函数：

```python
def save_failure(case: FailureCase) -> Path:
    """保存失败案例。"""

def load_all_failures() -> list[FailureCase]:
    """读取全部失败案例。"""

def find_similar_failures(current_stage: str, current_signals: list[str] = None) -> list[FailureCase]:
    """按阶段和信号查找相似失败案例。"""

def format_failures(cases: list[FailureCase]) -> str:
    """格式化失败案例列表。"""
```

Agent 入口：

```python
from engine.tools import failure

failure(action="list")
failure(action="add", ...)
```

失败案例适合记录：

- 明确流失的客户
- 报价失败
- 竞品抢单
- 跟进过度导致客户反感
- 决策链判断错误
- 没及时跟进导致窗口关闭

---

## 概念分层：事实档案 vs 分析归档

事实档案在概念上分两层：**evidence layer（事实层）** 和 **evaluation layer（分析归档）**。文件结构暂不重构，但 Agent 写入时必须区分。

| 维度 | 事实档案（evidence layer） | 分析归档（evaluation layer） |
| --- | --- | --- |
| 存储 | `data/customers/*.md`（notes/dates/events 段落） | `data/customers/*.md`（evaluations 段落）+ `data/outputs/analysis/` |
| 内容 | 客观事实、客户原话、事件、会面记录 | 阶段判断、诊断、策略、风险 |
| 写入工具 | `note()`、`date()`、`events()`、`sync_moments()` | `evaluate()`、`save_analysis()`、`save_from_markdown()` |
| 可变性 | 长期事实，尽量稳定 | 会随最新数据变化 |
| 可信度 | 高（冲突裁决优先级 2） | 低（冲突裁决优先级 6，最低） |
| 性质 | 输入层（Agent 推理的素材） | 输出层（Agent 推理的产物） |

**`person_evaluate` 归入分析归档**：虽然 `evaluate()` 写入的是客户档案文件，但概念上属于分析归档（evaluation layer），不是事实层。Agent 读档案时应区分"客户说的/做的"（evidence）和"Agent 判断的"（evaluation）。

例子：

```text
evidence（事实层，可写入）:
客户说"预算要老板审批"，6 月 30 日做过线上演示。

evaluation（分析归档，低优先级参考）:
客户处于方案展示后期，预算权限不在本人，下一步应确认决策链并约老板参与。
```

## 写入事实档案的自检清单

**核心原则**：事实档案是**输入层**，不是输出层。Agent 写入前必须自问："这条信息是我观察到的，还是我推断的？"

| ✅ 可以写入（客观事实） | ❌ 不可写入（主观判断） |
| --- | --- |
| 客户原话："我们的预算大概 10 万左右" | "客户预算充足，值得重点跟进" |
| 客户行为："3 次主动询问产品价格" | "客户购买意向很强" |
| 会面纪要："客户提到决策链有 3 人" | "客户应该快要成交了" |
| 事件记录："6/1-6/15 断联 15 天" | "客户已经不感兴趣了" |
| 用户补充："上次演示客户反馈不错" | "本月成交成功率 80%" |

**自检三问**（写入前必答）：

1. **这条信息是客户说的/做的，还是我推断的？** → 只能写前者
2. **如果换一个 Agent 读这条信息，会得出同样的结论吗？** → 如果不会，说明掺杂了判断
3. **这条信息 3 个月后还有效吗？** → 事实是稳定的，判断会过时

**特殊说明**：`evaluate()` 工具写入的"评估"是唯一例外——它允许 Agent 写主观判断，但必须**标注为"评估"而非"事实"**，存储位置和格式与事实分开。这是为了保留 Agent 的阶段性观点供未来参考，但不污染事实层。

---

## 数据流

```text
note("张三", "客户说预算审批需要老板确认")
  → engine.tools.note
  → engine.agent.write.agent_note
  → engine.facts.people_archive.append_note
  → data/customers/张三__person_xxx.md

events("张三", scan=True)
  → engine.tools.events
  → engine.agent.write.agent_events
  → engine.analyzers.events 检测事件
  → engine.facts.people_archive.append_event
  → 写入 ## 关系时间线

evidence("张三")
  → engine.tools.evidence
  → engine.agent.evidence.agent_evidence
  → 读取事实档案并格式化输出
```

---

## 注意事项

1. **不要绕过身份目录**：同一客户可能有多个微信号或别名，直接按文件名读写容易写错人。
2. **不要把主观判断写进事实档案**：策略、风险、阶段判断写入 analysis。
3. **追加优先**：`note()` 和 `date()` 都是追加写入，不覆盖已有内容。
4. **字段名兼容历史实现**：`关系时间线`、`Dates` 等字段名暂不改，避免破坏已有工具。
5. **真实联系人信息只留在本地私有数据目录**：不要写入公开文档、比赛材料或可推送代码。
6. **删除或合并档案要谨慎**：身份合并 `contact(merge)` 不可逆，必须先获得用户确认。
