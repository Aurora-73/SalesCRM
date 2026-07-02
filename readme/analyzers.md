# 分析器

## 概述

`engine/analyzers/` 包含所有纯数据计算模块：指标计算、排名引擎、事件检测、排除系统、周报生成。不依赖 LLM。

## 核心文件

| 文件 | 行数 | 功能 |
|------|------|------|
| `metrics.py` | 1117 | 16 指标计算 + neediness_penalty + interaction_pattern + 动态信号 + 销售指标 |
| `ranker.py` | 269 | 排名引擎（加权排序 + risers/fallers 检测） |
| `events.py` | ~300 | 活动时间线 / 事件检测（15 种事件类型 + 里程碑 + 5 个分类） |
| `exclude.py` | 300 | 5 层排除系统 + 账号合并管理 |
| `weekly_report.py` | 180 | 周报生成（排名快照 + Markdown 报告） |
| `chat_history.py` | ~100 | 聊天历史查询辅助 |

## 指标系统（metrics.py）

### 加权指标

| 指标 | 计算函数 | 含义 | 权重 |
|------|---------|------|------|
| `fback` | `compute_fback` | 回复字数比（客户/销售） | 0.10 |
| `rlatency` | `compute_rlatency` | 回复速度比（销售/客户） | 0.10 |
| `fback_quality` | `compute_fback_quality` | 回复质量（正向情绪+追问-敷衍） | 0.10 |
| `qscore_personal` | `compute_qscore_detailed` | 个人化问题比例（意向指标） | 0.10 |
| `trend` | 周变化计算 | composite 周变化 | 0.10 |
| `escore_volatility` | `compute_escore_volatility` | 情绪波动（会话间标准差） | 0.08 |
| `moments` | `compute_moments` | 朋友圈互动频率 | 0.06 |
| `qscore_functional` | `compute_qscore_detailed` | 工具化问题比例（需求信号） | 0.05 |
| `rlatency_context` | `compute_rlatency_context` | 慢回时有解释的比例 | 0.05 |
| `msg_volume_trend` | `compute_msg_volume_trend` | 消息量周变化率 | 0.05 |
| `latency_trend` | `compute_latency_trend` | 回复速度周变化率 | 0.05 |
| `recent` | `compute_recent` | 最后消息距今天数 | 0.05 |
| `active_days` | `compute_active_days` | 活跃天数（30 天意向） | 0.04 |
| `escore` | 内部计算 | 情绪表达比例 | 0.05 |
| `msg_count` | `compute_msg_count` | 消息总数（对数归一化） | 0.02 |

### 复合指标

| 指标 | 说明 |
|------|------|
| `composite` | 加权指标求和 |
| `neediness_penalty` | 乘法惩罚（0.4-1.0），消息量比>2 或发起频率>70% 时触发 |
| `base_score` | composite × neediness_penalty |
| `signal_level` | 强意向(≥0.70) / 中意向(≥0.50) / 弱意向(≥0.30) / 冷淡(≥0.15) / 无信号(<0.15) |
| `interaction_pattern` | buyer / evaluator / free_consulting / silent |

### 动态信号

| 信号 | 计算函数 | 说明 |
|------|---------|------|
| `session_recency` | `compute_session_recency` | 最近会话的活跃度 |
| `momentum` | `compute_momentum` | 互动动量（加速/减速） |
| `initiation_source` | `compute_initiation_source` | 谁先发起对话 |
| `media_engagement` | `compute_media_engagement` | 媒体互动（图片/视频/语音） |

### 销售特有指标（`compute_sales_metrics`）

| 指标 | 说明 |
|------|------|
| `meeting_count` | 提及见面/电话/会议的次数 |
| `budget_known` | 是否讨论过预算/价格 |
| `decision_chain` | 是否提及决策人/采购流程 |
| `urgency` | 紧迫性信号强度 |
| `competition` | 是否提及竞品/对比 |

### 入口函数

```python
def compute_metrics_for_contact(
    conn, config, contact_wxid, contact_name="",
    my_wxid=None, top_target=False
) -> Metrics:
    """计算单个联系人的全部指标。返回 Metrics 对象。"""
```

## 排名引擎（ranker.py）

```python
def compute_rankings(conn: sqlite3.Connection, config: Config) -> Ranking:
    """计算全部联系人排名。

    1. 获取所有有消息的联系人
    2. 应用排除过滤（filter_contacts）
    3. 按 person_id 聚合（多微信号合并）
    4. 计算每个 person 的 composite 分数
    5. 排序，检测 risers/fallers（delta ≥ 3 排名或 0.05 composite）
    6. 与上周快照对比
    7. 生成客户视图（hot/silent/urgent）
    """
```

### 排名变化检测

- **riser**：排名上升 ≥ 3 位，或 composite 上升 ≥ 0.05
- **faller**：排名下降 ≥ 3 位，或 composite 下降 ≥ 0.05
- 与 `data/outputs/rankings/` 下的上周 YAML 快照对比

### 客户排名视图

| 视图 | 条件 | 用途 |
|------|------|------|
| `hot_customers` | composite ≥ 0.5 | 高意向客户，优先跟进 |
| `silent_customers` | recent_raw > 7 天 | 长时间未互动，需要激活 |
| `urgent_customers` | urgency ≥ 0.3 | 紧迫信号，需要紧急处理 |

视图数据包含在 `Ranking` 对象中，同时 `format_ranking_table()` 会自动输出三个视图的列表。

## 活动时间线（events.py）

从聊天记录中自动提取关键关系事件，形成联系人的"关系时间线"。

### 核心函数

```python
def compute_timeline(
    conn, person, include_milestones=True, categories=None, max_events=50
) -> list[Event]:
    """生成完整的关系时间线。整合所有事件类型，按时间排序。"""

def detect_events(conn, person, disconnect_days=7) -> list[Event]:
    """检测基础事件（聊天频率、断联、销售进展等）。"""

def detect_milestones(conn, person) -> list[Event]:
    """检测里程碑事件（认识 N 天、消息破 N 条等）。"""

def format_timeline(events, group_by_month=True) -> str:
    """格式化时间线为可读文本，支持按月分组。"""
```

### 事件分类与类型

| 分类 | 事件类型 | 说明 |
|------|---------|------|
| 🏆 里程碑 | `FIRST_CHAT` | 首次聊天 |
| 🏆 里程碑 | `FIRST_DATE` | 首次约见 |
| 🏆 里程碑 | `MILESTONE` | 关系里程碑（认识 N 天、消息破 N 条） |
| 🏆 里程碑 | `FIRST_MEETING` | 首次会面（销售特有） |
| 🏆 里程碑 | `DEAL_CLOSE` | 成交（销售特有） |
| 💬 沟通动态 | `FREQUENCY_UP` | 聊天频率上升 |
| 💬 沟通动态 | `FREQUENCY_DOWN` | 聊天频率下降 |
| 💬 沟通动态 | `DISCONNECT` | 断联 |
| 💬 沟通动态 | `RECONNECT` | 恢复联系 |
| 📈 信号变化 | `SIGNAL_LEVEL_UP` | 意向等级提升 |
| 📈 信号变化 | `SIGNAL_LEVEL_DOWN` | 意向等级下降 |
| 📝 信息更新 | `INFO_UPDATE` | 档案信息更新 |
| 💰 销售进展 | `REQUIREMENT_CONFIRM` | 需求确认（销售特有） |
| 💰 销售进展 | `DECISION_MAKER_APPEAR` | 决策人出现（销售特有） |
| 💰 销售进展 | `PROPOSAL_SENT` | 报价发送（销售特有） |

### 里程碑自动检测

| 类型 | 检测条件 |
|------|---------|
| 认识天数 | 100 天、365 天、1000 天 |
| 消息数量 | 100 条、500 条、1000 条、5000 条、10000 条 |

### Event 数据结构

```python
@dataclass
class Event:
    event_type: EventType       # 事件类型枚举
    date: str                   # YYYY-MM-DD
    detail: str                 # 详细描述
    confidence: float = 1.0     # 置信度 (0-1)
    category: TimelineCategory  # 事件分类
    metadata: dict              # 附加元数据

    def to_dict(self) -> dict:  # 序列化为 dict
```

## 排除系统（exclude.py）

5 层排除，按优先级从高到低：

| 层 | 检查内容 | 说明 |
|---|---------|------|
| 1 | `is_hard_excluded(wxid)` | 系统账号、用户自己 |
| 2 | 微信标签 | "非客户"、"放弃"、"群友" |
| 3 | 联系人类型 | `former_friend`（已删除好友） |
| 4 | `contact_excludes` 表 | 手动排除记录 |
| 5 | 配置关键词 | config 中的排除关键词 |

```python
def filter_contacts(conn, my_wxid) -> tuple[list[dict], list[dict]]:
    """返回 (included, excluded) 两个列表。

    included 中会标记 "重点客户" 等标签。
    """
```

### 账号合并

`contact_merges` 表记录"哪个 wxid 合并到哪个 canonical_wxid"。`filter_contacts` 合并时会把被合并账号的消息计入主账号。

## 周报（weekly_report.py）

```python
def generate_weekly_report(conn, config, deep=False) -> str:
    """生成周报 Markdown。

    1. compute_rankings() 获取排名
    2. 保存 YAML 快照到 data/outputs/rankings/
    3. 格式化 Markdown（排名表 + risers/fallers + 数据不足列表）
    """
```

## 数据流

```
tools.py: metrics('张三')
    ↓
report.py: agent_metrics → compute_metrics_for_contact(conn, config, wxid)
    ↓
analyzers/metrics.py: compute_* 函数
    ↓
返回 Metrics 对象（engine/models/metrics.py）

tools.py: rank()
    ↓
report.py: agent_rank → compute_rankings(conn, config)
    ↓
analyzers/ranker.py: filter_contacts + compute_metrics + sort
    ↓
返回 Ranking 对象（engine/models/ranking.py）
```

## 注意事项

1. **指标意向**：大部分指标默认 30 天意向，`active_days` 也是 30 天。可通过 config 调整。
2. **会话分割**：`rlatency` 等指标需要定义"什么是同一个会话"。默认连续消息间隔 > 4 小时视为不同会话。
3. **neediness_penalty**：乘法惩罚，不是加法。消息量比（你/客户）> 2 或发起频率 > 70% 时触发，最低打到 0.4。
4. **排名快照**：周报会保存 YAML 快照到 `data/outputs/rankings/`，用于检测排名变化。
5. **排除不可逆**：手动排除后，排名中不再出现该联系人，但消息数据不受影响。