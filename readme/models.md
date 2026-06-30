# 数据模型

## 概述

`engine/models/` 定义系统中所有数据结构。全部是纯 Python dataclass，支持 YAML 序列化。不包含业务逻辑。

## 核心文件

| 文件 | 行数 | 关键类 |
|------|------|--------|
| `metrics.py` | 162 | `MetricValue`, `Metrics`, `DeltaInfo` |
| `ranking.py` | 104 | `RankedPerson`, `Ranking`, `RankingChange`, `InsufficientData` |
| `stage.py` | 118 | `Stage`, `StageState`, `StageOverride`, `EvidenceEntry` |
| `event.py` | 40 | `Event` |
| `failure.py` | 77 | `FailureCase`, `FailurePattern` |
| `profile.py` | 72 | `Profile`（继承 EntityBase） |
| `strategy.py` | 71 | `Strategy`, `Action`, `Risk` |
| `evaluation.py` | 54 | `Evaluation`, `TimelineEntry` |
| `date_review.py` | 54 | `DateReview` |
| `base.py` | 46 | `EntityBase`（YAML 序列化基类） |

## MetricValue（单个指标）

```python
@dataclass
class MetricValue:
    raw: float           # 原始值
    normalized: float    # 归一化到 [0, 1]
    confidence: float    # 置信度（样本量越少越低）
    sample_size: int     # 计算用的样本数
```

## Metrics（指标集合）

```python
@dataclass
class Metrics:
    # 指标字段（每个都是 MetricValue）
    fback: MetricValue
    rlatency: MetricValue
    fback_quality: MetricValue
    qscore_personal: MetricValue
    trend: MetricValue
    escore_volatility: MetricValue
    moments: MetricValue
    qscore_functional: MetricValue
    rlatency_context: MetricValue
    msg_volume_trend: MetricValue
    latency_trend: MetricValue
    recent: MetricValue
    active_days: MetricValue
    escore: MetricValue
    msg_count: MetricValue

    # 复合指标
    neediness_penalty: float  # 乘法惩罚 (0.4-1.0)
    interaction_pattern: str  # "buyer" / "evaluator" / "free_consulting" / "silent"
    composite: float          # 最终加权分数
    signal_level: str         # "强意向" / "中意向" / "弱意向" / "冷淡" / "无信号"
    base_score: float         # composite × neediness_penalty

    # 动态信号
    session_recency: dict
    momentum: dict
    initiation_source: dict
    media_engagement: dict

    # 变化
    delta: DeltaInfo | None  # 与上周对比
```

## RankedPerson（排名条目）

```python
@dataclass
class RankedPerson:
    rank: int              # 排名（1-based）
    name: str              # 显示名
    person_id: str
    wxid: str
    base_score: float      # 加权分数
    composite: float       # 最终分数
    signal_level: str      # 信号等级
    delta_rank: int | None # 排名变化（正=上升，负=下降）
    delta_composite: float | None
    tags: list[str]        # ["riser", "faller", "重点客户"]
    insufficient_data: bool
    
    # 新增字段（用于客户视图分类）
    interaction_pattern: str  # "buyer" / "evaluator" / "free_consulting" / "silent"
    urgency: float            # 紧迫性信号 (0.0-1.0)
    recent_raw: int           # 最近消息距今天数（原始值）
```

## Ranking（排名集合）

```python
@dataclass
class Ranking:
    week: str                       # "2026-W24"
    generated_at: str
    rankings: list[RankedPerson]    # 按 composite 降序
    risers: list[RankedPerson]      # 排名上升的客户
    fallers: list[RankedPerson]     # 排名下降的客户
    insufficient_data: list[InsufficientData]  # 数据不足的客户
    
    # 新增字段（客户排名视图）
    hot_customers: list[RankedPerson]      # composite ≥ 0.5 的高意向客户
    silent_customers: list[RankedPerson]   # recent_raw > 7 天未活跃的客户
    urgent_customers: list[RankedPerson]   # urgency ≥ 0.3 的紧急客户
```

## Stage（销售阶段）

阶段的生命周期：

```python
STAGES = [
    "未识别",        # 没有足够数据判断
    "潜客获取",      # 获取联系方式，建立初步连接
    "初步接触",      # 建立信任，展示产品价值
    "需求确认",      # 深入了解痛点，确认决策链
    "方案展示",      # 定制方案，逐步确认意向
    "谈判/报价",     # 价格谈判，异议处理，逼单
    "成交",          # 签合同，收款
    "售后/复购",     # 售后跟进，增购/转介绍
    "冷淡/停滞",     # 兴趣下降，互动减少
    "退出/失败",     # 基本不再联系或明确拒绝
]
```

**销售阶段流程图**：

```
潜客(Lead) → 初步接触 → 需求确认 → 方案展示 → 谈判/报价 → 成交 → 售后/复购
                                   ↓                    ↓
                               流失/沉默            流失/沉默
```

```python
@dataclass
class Stage:
    state: StageState       # 当前阶段状态
    override: StageOverride | None  # 手动覆盖
    evidence: list[EvidenceEntry]   # 阶段变化证据

    @property
    def effective_stage(self) -> str:
        """优先返回 override，否则返回 state.current。"""
```

## Event（销售事件）

```python
@dataclass
class Event:
    event_type: str   # FIRST_CHAT / DISCONNECT / RECONNECT / FREQUENCY_UP / FREQUENCY_DOWN / REQUIREMENT_CONFIRM / DECISION_MAKER_APPEAR / PROPOSAL_SENT
    date: str         # "2026-06-01"
    detail: str       # 描述
    metadata: dict    # 附加数据
```

## FailureCase（失败案例）

```python
@dataclass
class FailureCase:
    person: str
    date: str
    stage: str
    signals: list[str]
    diagnosis: str
    lessons: list[str]
    patterns: list[FailurePattern]  # 关联的失败模式
```

## Strategy（策略）

```python
@dataclass
class Strategy:
    actions: list[Action]  # 推荐行动列表
    risks: list[Risk]      # 风险列表
    reasoning: str         # 推理过程

@dataclass
class Action:
    description: str
    priority: str   # "high" / "medium" / "low"
    timing: str     # "now" / "next_conversation" / "next_meeting"

@dataclass
class Risk:
    description: str
    severity: str   # "high" / "medium" / "low"
    mitigation: str # 缓解措施
```

## YAML 序列化

所有 model 都支持 `to_dict()` / `from_dict()` 方法，通过 `EntityBase` 基类实现。

```python
from engine.models.metrics import Metrics
m = Metrics(...)
data = m.to_dict()  # → dict
m2 = Metrics.from_dict(data)  # → Metrics
```

排名快照存储在 `data/outputs/rankings/` 下，格式为 YAML。

## 注意事项

1. **MetricValue.confidence**：样本量少于 10 条消息时，confidence 会显著下降。`ranker.py` 会把低信心的客户放入 `insufficient_data` 列表。
2. **Stage 与 metrics 的关系**：Stage 是离散的状态，metrics 是连续的 [0,1] 分数。Stage 判断需要结合两者。
3. **DeltaInfo**：只有在有上周快照时才非 None。首次运行周报时 delta 全部为 None。
4. **Interaction pattern**：通过消息量比、发起频率、回复质量综合判断。"evaluator" 表示客户在评估阶段。