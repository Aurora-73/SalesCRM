# 销售决策公式

## 概述

`engine/formulas.py` 实现核心销售决策公式 + 辅助公式 + 决策函数，用于量化分析"客户到底有没有意向"和"现在该不该推进"。

## 核心文件

| 文件 | 行数 | 功能 |
|------|------|------|
| `engine/formulas.py` | 518 | 全部公式实现（销售决策公式） |

## 工作流程

公式分两步：自动参数 + 手动参数。Agent 先调 `sales_params` 获取可自动计算的值，再根据聊天内容判断手动参数，最后代入公式。

```python
from engine.tools import sales_params, sales_bq, sales_bsp, sales_bws, sales_action

# 第一步：自动参数
params = sales_params("张三")
# → {auto: {Sp, Fback, Rlatency, ...}, manual: {Pface, Ddepth, ...}}

# 第二步：Agent 判断 manual 参数
# 第三步：代入公式
bq = sales_bq(sp=0.7, fback=0.8, user_investment=0.3, pface=0.4)
bsp = sales_bsp(user_ddepth=0.6, target_ddepth=0.5, target_latency=1.2, user_latency=0.8)
bws = sales_bws(gap_effect=0.3, cp_index=0.5, eev=0.4, scarcity_loss=0.1)

# 第四步：终极决策
action = sales_action(bq=bq["bq"], bsp=bsp["bsp"], bws=bws["bws"])
# → {"action": "进攻" / "拉扯" / "重置" / "维持"}
```

## 核心销售公式

### BQ（购买意愿真实度）

```
BQ = Sp × log(Fback + 1) / (User_Investment × Pface)
```

| 参数 | 含义 | 来源 |
|------|------|------|
| `Sp` | 显示性偏好（客户对你产品有兴趣的信号强度） | auto：qscore_personal × 1.5 + fback_quality × 0.3 |
| `Fback` | 回复字数比（客户/销售） | auto：fback.normalized |
| `User_Investment` | 我方投入程度 | auto：1.0 - neediness_penalty |
| `Pface` | 面子阻力（客户维持形象的防备程度） | **manual**：0.1-0.9 |

**阈值**：>1.0 真实意向，<0.5 真实没戏

### BSP（商务势能）

```
BSP = (Ddepth / Target_Ddepth) × (Target_Latency / User_Latency)
```

| 参数 | 含义 | 来源 |
|------|------|------|
| `Ddepth` | 你的战略纵深（信息保留、底牌保留） | **manual**：0.1-0.9 |
| `Target_Ddepth` | 客户的战略纵深 | **manual**：0.1-0.9 |
| `Target_Latency` | 客户的回复延迟 | auto：rlatency 反推 |
| `User_Latency` | 你的回复延迟 | auto：rlatency 推导 |

**阈值**：0.8-1.5 健康，<0.6 红线阻断

### BWS（购买意向期）

```
BWS = (Gap_Effect × Cp_Index) + EEV - Scarcity_Loss
```

| 参数 | 含义 | 来源 |
|------|------|------|
| `Gap_Effect` | 情绪落差（Act - Exp） | auto |
| `Cp_Index` | 服从阶梯（客户对微小指令的顺从程度） | **manual**：0.0-1.0 |
| `EEV` | 成交期望值 | auto |
| `Scarcity_Loss` | 稀缺性损耗 | auto：消息量趋势+延迟趋势 |

**阈值**：>0.8 出击信号，<0.3 意向关闭

### PV（成交期望值）

```
PV = Backstage / (Pface + 1.0)
```

| 参数 | 含义 | 来源 |
|------|------|------|
| `Backstage` | 后台暴露度（客户展示内部信息/预算/决策流程的程度） | **manual**：0.1-0.9 |
| `Pface` | 面子阻力 | **manual** |

**阈值**：>0.5 高期望值

### BS（矛盾状态，待实现）

```
BS = Internal_D - External_R
```

| 参数 | 含义 | 来源 |
|------|------|------|
| `Internal_D` | 内在购买欲望 | **manual** |
| `External_R` | 外部阻力（预算/决策链/竞品） | **manual** |

**阈值**：>0 欲望占主导

**状态**：❌ 未实现（待开发）

## 辅助公式

### Gap_Effect（情绪落差）

```
Gap_Effect = Act - Exp
```

`Act` = 实际情绪表现，`Exp` = 心理预期。正数 = 惊喜，负数 = 失望。

### EEV（成交期望值）

```
EEV = (P_succ × bonus) - (P_fail × risk)
```

`P_succ` = 成功概率，`bonus` = 成功收益，`P_fail` = 失败概率，`risk` = 失败代价。

## 自动参数推导

`sales_params(name)` 从数据库指标推导以下 auto 参数：

| auto 参数 | 推导逻辑 |
|----------|---------|
| `Sp` | max(0.1, qscore_personal × 1.5 + fback_quality × 0.3) |
| `Fback` | fback.normalized |
| `Fback_quality` | fback_quality.normalized |
| `Rlatency` | rlatency.normalized |
| `Ve` | escore.normalized（情绪效价） |
| `EV` | escore_volatility.normalized（情绪波动） |
| `S_cost` | log(1+msg_count)/log(500) × 0.5 + active_days/90 × 0.5（沉没成本） |
| `Noise` | (1-fback_quality) × 0.5 + qscore_functional × 0.3（言语掩饰） |
| `Exp` | 0.5 + rlatency × 0.3（心理预期） |
| `User_Investment` | 1.0 - neediness_penalty |
| `Scarcity_Loss` | (0.8-msg_vol_trend) × 0.3 + (0.8-latency_trend) × 0.2 |

## sales_action 决策函数

```python
def sales_action(bq, bsp, bws, bs=0.0, ev=0.5) -> dict:
    """终极决策。返回 {"action": "...", "reasoning": "..."}。"""
```

| 条件 | 决策 |
|------|------|
| BQ > 1.0 且 BWS > 0.8 | **进攻** |
| BQ > 0.5 且 BSP 在 0.8-1.5 | **拉扯** |
| BQ < 0.5 且 BSP < 0.6 | **重置** |
| 其他 | **维持** |

## 数据流

```
tools.py: sales_params('张三')
    ↓
formulas.py: 自动连接 DB → compute_metrics_for_contact → 推导 auto 参数
    ↓
返回 {auto: {...}, manual: {Pface: {hint, range, default}, ...}}

Agent 根据聊天内容判断 manual 参数值
    ↓
sales_bq(sp, fback, user_investment, pface)
    ↓
返回 {"bq": 1.23, "interpretation": "真实意向", ...}
```

## 注意事项

1. **manual 参数是关键**：auto 参数只提供基础数据，真正区分分析质量的是 Agent 对 Pface/Ddepth/Backstage 的判断。
2. **sales_params 可接受外部连接**：默认自己开 DB 连接，也支持 `conn` 参数传入，避免重复连接。
3. **公式来自 chat-skills 项目**：原项目已删除，公式提取到此处并适配销售场景。公式本身的合理性由销售知识库方法论保证。
4. **不要死记阈值**：阈值是参考，不是硬规则。BQ=0.9 不一定比 BQ=1.1 差，要结合上下文。
5. **参数校验**：所有公式函数对参数做类型校验（必须是数字），非数字参数会返回错误消息而非抛异常。
6. **公式稳定性**：所有公式函数对参数做类型校验，非数字参数会返回错误消息而非抛异常。