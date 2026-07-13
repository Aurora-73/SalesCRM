# 数据模型

## 概述

`engine/models/` 定义系统中所有数据结构。全部是纯 Python dataclass，支持 YAML 序列化。不包含业务逻辑。

## 核心文件

| 文件 | 行数 | 关键类 |
|------|------|--------|
| `metrics.py` | 181 | `MetricValue`, `Metrics`, `DeltaInfo` |
| `ranking.py` | 124 | `RankedPerson`, `Ranking`, `RankingChange`, `InsufficientData` |
| `stage.py` | 118 | `Stage`, `StageState`, `StageOverride`, `EvidenceEntry` |
| `event.py` | 40 | `Event` |
| `failure.py` | 77 | `FailureCase`, `FailurePattern` |
| `profile.py` | 93 | `Profile`（继承 EntityBase，支持自定义字段） |
| `strategy.py` | 71 | `Strategy`, `Action`, `Risk` |
| `evaluation.py` | 54 | `Evaluation`, `TimelineEntry` |
| `date_review.py` | 50 | `DateReview` |
| `deal.py` | 89 | `Deal`, `DealStage`, `DealHistory`, `ContactInfo` |
| `base.py` | 46 | `EntityBase`（统一元数据基类） |

## MetricValue（单个指标）

```python
@dataclass
class MetricValue:
    raw: float           # 原始值
    normalized: float    # 归一化到 [0, 1]
    confidence: float    # 置信度（样本量越少越低）
    sample_size: int     # 计算用的样本数
    extra: dict          # 附加数据（可选）
```

## Metrics（指标集合）

```python
@dataclass
class Metrics:
    # 复合指标
    _id: str
    base_score: float         # composite × neediness_penalty
    composite: float          # 最终加权分数
    signal_level: str         # "强意向" / "中意向" / "弱意向" / "冷淡" / "无信号"
    top_target_bonus: bool

    # 原始指标（每个都是 MetricValue）
    fback: MetricValue
    rlatency: MetricValue
    qscore: MetricValue
    escore: MetricValue
    moments: MetricValue
    msg_count: MetricValue
    active_days: MetricValue
    recent: MetricValue
    trend: MetricValue

    # 新增指标
    fback_quality: MetricValue
    escore_volatility: MetricValue
    qscore_personal: MetricValue
    qscore_functional: MetricValue
    rlatency_context: MetricValue
    msg_volume_trend: MetricValue
    latency_trend: MetricValue

    # 跟进投入惩罚（乘法系数，不参与加权）
    neediness_penalty: float  # 0.4-1.0
    volume_ratio: float
    initiation_ratio: float
    interaction_pattern: str  # "buyer" / "evaluator" / "free_consulting" / "silent"

    # 动态信号（不参与 composite 加权）
    session_recency: dict
    momentum: dict
    initiation_source: dict
    media_engagement: dict

    # 销售特有指标（不参与 composite 加权，仅用于销售决策公式）
    meeting_count: int
    deal_stage: int
    budget_known: int
    decision_chain: float
    competition: float
    urgency: float

    # 变化
    delta: DeltaInfo  # 与上周对比

    def all_metrics(self) -> dict[str, MetricValue]:
        """返回所有参与加权的 MetricValue 字段。"""
```

## DeltaInfo

```python
@dataclass
class DeltaInfo:
    composite: float  # composite 变化
    rank: int         # 排名变化
```

## RankedPerson（排名条目）

```python
@dataclass
class RankedPerson:
    rank: int              # 排名（1-based）
    name: str              # 显示名
    _id: str               # 向后兼容，等于 person_id
    person_id: str         # identity 系统的 person_id
    base_score: float      # 加权分数
    composite: float       # 最终分数
    signal_level: str      # 信号等级
    stage: str             # 当前销售阶段
    delta_rank: int        # 排名变化（正=上升，负=下降）
    delta_composite: float # composite 变化
    tags: list[str]        # ["riser", "faller", "重点客户"]

    # 客户视图分类字段
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
    total_candidates: int           # 总候选人数
    rankings: list[RankedPerson]    # 按 composite 降序
    risers: list[RankingChange]     # 排名上升的客户
    fallers: list[RankingChange]    # 排名下降的客户
    insufficient_data: list[InsufficientData]  # 数据不足的客户
    strategy_summary: list[dict]    # 策略摘要

    # 客户排名视图
    hot_customers: list[RankedPerson]      # composite ≥ 0.5 的高意向客户
    silent_customers: list[RankedPerson]   # recent_raw > 7 天未活跃的客户
    urgent_customers: list[RankedPerson]   # urgency ≥ 0.3 的紧急客户
```

## RankingChange / InsufficientData

```python
@dataclass
class RankingChange:
    name: str
    reason: str

@dataclass
class InsufficientData:
    name: str
    message_count: int
    status: str  # "数据不足，不参与排名"
```

## Stage（销售阶段）

阶段的生命周期：

```python
STAGES = [
    "未识别",        # 没有足够数据判断
    "线索",          # 获取联系方式，建立初步连接
    "初步接触",      # 建立信任，展示产品价值
    "深入沟通",      # 深入了解痛点，确认决策链
    "已会面",        # 完成首次会面
    "持续跟进",      # 持续沟通，推进关系
    "方案推进",      # 定制方案，逐步确认意向
    "签约确认",      # 签合同，收款
    "退出/失败",     # 基本不再联系或明确拒绝
]
```

**销售阶段流程图**：

```
线索 → 初步接触 → 深入沟通 → 已会面 → 持续跟进 → 方案推进 → 签约确认
                              ↓                    ↓
                          流失/沉默            流失/沉默
```

```python
@dataclass
class StageState:
    current_stage: str           # 当前阶段
    entered_at: str              # 进入时间
    days_in_current_stage: int   # 在当前阶段的天数
    is_stagnant: bool            # 是否停滞
    next_stage: str              # 下一阶段
    advancement_signals: list[str]  # 推进信号
    blockers: list[str]          # 阻碍因素

@dataclass
class StageOverride:
    stage: str                   # 覆盖的阶段
    reason: str                  # 覆盖原因
    overridden_at: str           # 覆盖时间

@dataclass
class EvidenceEntry:
    date: str
    event: str
    source: str
    metrics_snapshot: dict
    stage_change: str

@dataclass
class Stage:
    stage_state: StageState
    stage_override: StageOverride | None
    evidence_chain: list[EvidenceEntry]

    @property
    def effective_stage(self) -> str:
        """优先返回 override，否则返回 stage_state.current_stage。"""
```

## Event（销售事件）

```python
@dataclass
class Event:
    _id: str
    timestamp: str        # ISO 格式时间戳
    event_type: str       # FIRST_CHAT / DISCONNECT / RECONNECT / FREQUENCY_UP / FREQUENCY_DOWN / REQUIREMENT_CONFIRM / DECISION_MAKER_APPEAR / PROPOSAL_SENT
    content: str          # 事件内容描述
    source: str           # "manual" / "auto" / 其他来源
    confidence: float     # 置信度 (0-1)
    tags: list[str]       # 事件标签
    ref: str              # 关联引用
```

## Profile（联系人档案）

联系人基础档案，继承自 `EntityBase`，支持 YAML 序列化。

```python
@dataclass
class Profile(EntityBase):
    name: str = ""
    wxid: str = ""
    wechat_id: str = ""
    nickname: str = ""
    remark: str = ""
    tags: list[str] = field(default_factory=list)
    description: str = ""
    added_date: str = ""
    age: int | None = None
    occupation: str = ""

    custom_fields: dict[str, str] = field(default_factory=dict)
```

### 自定义字段（custom_fields）

支持任意键值对的扩展字段，用于存储项目特有、不想硬编码到模型中的数据。

```python
# 设置自定义字段
profile.set_custom("company", "ABC科技")
profile.set_custom("position", "产品经理")

# 获取自定义字段
company = profile.get_custom("company")       # "ABC科技"
unknown = profile.get_custom("not_exist")      # ""
unknown2 = profile.get_custom("not_exist", "默认值")  # "默认值"

# 删除自定义字段
profile.remove_custom("company")
```

**YAML 序列化规则**：
- `custom_fields` 非空时才会出现在 YAML 中
- 旧版 YAML 没有 custom_fields 字段，加载时默认为空 dict
- 完全向后兼容

### 从微信同步创建

```python
profile = Profile.from_wechat_row(row)  # 从 contacts 表行创建
```

## FailureCase（失败案例）

```python
@dataclass
class FailurePattern:
    category: str   # 失败类别
    detail: str     # 失败详情

@dataclass
class FailureCase:
    person_id: str          # 关联的 person_id（可选）
    person: str             # 人物名称（显示用）
    date: str               # 发生日期
    stage: str              # 当时所处阶段
    cause: str              # 失败原因（一句话）
    signals: list[str]      # 失败信号
    outcome: str            # 结果
    lesson: str             # 教训
    duration_months: int    # 持续月数
    stage_reached: str      # 达到的阶段
    failure_reasons: list[FailurePattern]  # 失败原因列表
    error_patterns: list[str]              # 错误模式
    lessons: list[str]                     # 教训列表
    retrospective_detection: bool          # 是否事后检测
    detection_signals: list[str]           # 检测信号
    created_at: str                        # 创建时间
```

## Strategy（策略）

```python
@dataclass
class Action:
    priority: int    # 优先级（数字越大越优先）
    action: str      # 行动描述
    detail: str      # 行动详情
    reason: str      # 行动原因

@dataclass
class Risk:
    description: str  # 风险描述
    source: str       # 风险来源
    severity: str     # "high" / "medium" / "low"

@dataclass
class Strategy:
    _id: str
    current_stage: str          # 当前销售阶段
    heat_level: float           # 热度等级 (0-1)
    customer_intent: str        # 客户意向 ("none" / "weak" / "strong" 等)
    advancement_risk: str       # 推进风险 ("low" / "medium" / "high")
    actions: list[Action]       # 推荐行动列表
    risks: list[Risk]           # 风险列表
    knowledge_refs: list[str]   # Wiki 知识引用
```

## Deal（商机/交易）

```python
@dataclass
class DealStage:
    stage_id: str       # 阶段 ID
    stage_name: str     # 阶段名称
    order: int          # 阶段顺序
    probability: float  # 成交概率

@dataclass
class DealHistory:
    timestamp: str      # 变更时间
    stage_id: str       # 阶段 ID
    stage_name: str     # 阶段名称
    reason: str         # 变更原因

@dataclass
class Deal(EntityBase):
    person_id: str           # 关联客户 ID
    person_name: str         # 客户名称
    title: str               # 商机标题
    description: str         # 商机描述
    amount: float            # 金额
    currency: str            # 币种（默认 CNY）
    current_stage: str       # 当前阶段
    stage_probability: float # 阶段成交概率
    expected_close_date: str # 预计成交日期
    actual_close_date: str   # 实际成交日期
    status: str              # "open" / "won" / "lost"
    competition: str         # 竞品情况
    contacts: list[str]      # 联系人列表
    notes: str               # 备注
    stage_history: list[DealHistory]  # 阶段变更历史

    @classmethod
    def create(cls, person_id, person_name, title, amount=0.0, stage="lead") -> "Deal":
        """创建新商机。"""

    def advance_stage(self, stage_id, stage_name, reason=""):
        """推进到下一阶段。"""

    def close(self, success: bool, reason=""):
        """关闭商机（成功/失败）。"""

@dataclass
class ContactInfo:
    company: str        # 公司
    position: str       # 职位
    industry: str       # 行业
    phone: str          # 电话
    email: str          # 邮箱
    address: str        # 地址
    decision_role: str  # 决策角色
    department: str     # 部门
```

## Evaluation（评估/验证）

```python
@dataclass
class TimelineEntry:
    date: str
    event: str
    result: str

@dataclass
class Evaluation:
    invited: bool              # 是否邀请
    accepted: bool             # 是否接受
    dated: bool                # 是否会面
    date_feedback: str         # 会面反馈
    continuing: bool           # 是否继续
    entered_failure: bool      # 是否进入失败
    timeline: list[TimelineEntry]  # 时间线
```

## DateReview（会面复盘）

```python
@dataclass
class DateReview:
    date: str                    # 会面日期
    location: str                # 地点
    duration_hours: float        # 时长（小时）
    cost: float                  # 花费
    activities: list[str]        # 活动内容
    initiator: str               # 发起方 ("me" / "client")
    client_mood: str             # 客户情绪
    key_discussion: bool         # 是否有关键讨论
    client_response: str         # 客户反应
    client_engagement_level: str # 客户参与度 ("low" / "medium" / "high")
    comfort_level: str           # 舒适度 ("low" / "medium" / "high")
    clear_positive_feedback: bool # 是否有明确正面反馈
    my_performance_score: int    # 我方表现评分 (1-5)
    topic_distribution: dict     # 话题分布
    what_went_well: list[str]    # 做得好的方面
    what_could_improve: list[str] # 可改进的方面
    next_step: str               # 下一步
    next_meeting_urgency: str    # 下次会面紧迫性 ("low" / "medium" / "high")
    rating: int                  # 总体评分 (1-5)
```

## EntityBase（统一元数据基类）

```python
@dataclass
class EntityBase:
    """所有实体必须携带的统一元数据。"""
    _id: str = ""
    source: str = ""
    created_at: str = ""    # ISO 格式
    updated_at: str = ""    # ISO 格式
    version: int = 1
    confidence: float = 1.0
    privacy_level: str = "private"

    def touch(self):
        """更新 updated_at 并递增 version。"""
        self.updated_at = now_iso()
        self.version += 1
```

## YAML 序列化

各模型按需实现自己的序列化方法，并非全部通过 EntityBase 统一实现：

- **EntityBase 子类**（Profile、Deal）：继承 `touch()` 方法，自行实现 `to_yaml()` / `from_yaml()`
- **独立模型**（Metrics、Ranking、Stage、Event、FailureCase、Strategy、Evaluation、DateReview）：各自实现 `to_yaml()` / `from_yaml()` 或 `to_dict()` / `from_dict()`
- **简单模型**（RankedPerson、RankingChange、InsufficientData、Action、Risk 等）：实现 `to_dict()` / `from_dict()`

排名快照存储在 `data/outputs/rankings/` 下，格式为 YAML。

## 注意事项

1. **MetricValue.confidence**：样本量少于 10 条消息时，confidence 会显著下降。`ranker.py` 会把低信心的客户放入 `insufficient_data` 列表。
2. **Stage 与 metrics 的关系**：Stage 是离散的状态，metrics 是连续的 [0,1] 分数。Stage 判断需要结合两者。
3. **DeltaInfo**：只有在有上周快照时才非 None。首次运行周报时 delta 全部为默认值。
4. **Interaction pattern**：通过消息量比、发起频率、回复质量综合判断。"evaluator" 表示客户在评估阶段。
5. **销售特有指标**：meeting_count、deal_stage、budget_known 等字段不参与 composite 加权，仅用于销售决策公式参考。
6. **Deal 与 Stage 的区别**：Stage 是客户关系阶段（全局），Deal 是具体商机/交易（可以有多个）。一个客户可以有多个 Deal。
