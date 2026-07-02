# 公式参考（辅助视角）

> **定位声明**：公式是 chat-skills 遗产的独立体系，通过标注 Wiki 依据做**软关联**（非派生）。Agent 用公式核验判断，不机械套阈值。Wiki 知识库才是推理主轴，详见 [PROJECT.md 2.5](PROJECT.md#25-wiki-知识库推理主轴)。

## 目标 vs 现状（显式标注）

| 维度 | 目标状态（架构.md 描述） | 当前状态（代码现实） |
|------|------------------------|---------------------|
| 公式来源 | 从 Wiki 知识派生，三源融合 | chat-skills 遗产的独立体系 |
| 公式与 Wiki 关系 | 派生子集（Wiki 是"老师"，公式是"老师讲的公式"） | 软关联（通过标注 Wiki 依据条目建立关联，非派生） |
| 权重来源 | Wiki 知识派生 + 回测调参 | 经验启发值，部分已通过回测校准 |
| 演进路径 | 补齐 Wiki 依据标注 → 结构化元数据 → 逐步回测校准 → 最终实现派生关系 | 见 [plan/矫正计划.md](../plan/矫正计划.md) P1-P6 任务 |

**当前公式定位**：辅助参考视角，Agent 核验而非套用。公式结果不主导决策，仅作量化视角参考。

## 公式演进链条

**叙事诚实**：公式不是从 Wiki 派生的，而是 chat-skills 遗产的独立体系。演进路径如下：

```
chat-skills 遗产公式（独立体系）
    ↓ 标注 Wiki 依据（软关联）—— P1 任务 7 已完成
    ↓ 未来回测校准（权重和阈值）—— P6 任务待实施
    ↓ 迭代优化（逐步实现派生关系）—— 长期目标
```

**权重和阈值的来源**：

| 维度 | 当前状态 | 目标状态 |
|------|---------|---------|
| 权重 | 经验启发值，部分已通过实际案例校准 | 通过回测数据校准（P6 任务） |
| 阈值 | 经验启发值，参考 chat-skills 原项目 | 通过实际成交/流失案例回测校准 |
| 与 Wiki 关系 | 软关联（docstring 标注 Wiki 依据） | 结构化元数据 + 测试校验（P6 任务） |

**当前进度**：第一阶段（标注 Wiki 依据）已完成 7 个公式（IVI/SPE/EWS/Gap_Effect/BQ/BSP/BWS），第二阶段（回测校准）待 P6 任务实施。详见 [plan/矫正计划.md](../plan/矫正计划.md) 任务 14。

## 公式的三个来源

| 来源 | 例子 | 在公式中的体现 |
|------|------|--------------|
| **Wiki 知识库** | `[[购买意向指标]]` 说"回复速度变化反映意向" | BSP 公式中的延迟因子 |
| **GitHub 公开方法论** | 开源销售/社交动力学框架 | BQ 等公式的概念结构借鉴 |
| **历史案例反馈** | 实际成交/流失案例的复盘 | 权重和阈值的回测校准（待实现） |

三者都归入"原始知识文件"——GitHub 方法论和书籍课程一样，都是外部知识输入。**当前公式只是与 Wiki 软关联，未实现完整派生**（详见"目标 vs 现状"表）。

## 公式与 Wiki 的关系

每个公式函数的 docstring 标注了对应的 Wiki 条目（如果存在）。Agent 核验公式结果时，应同时查阅对应 Wiki 条目做交叉验证。

| 公式 | 对应 SalesCRM Wiki 条目 | 关系 |
|------|------------------------|------|
| `sales_bq` / `formula_ivi` | `[[购买意向指标]]` | 软关联 |
| `sales_bsp` / `formula_spe` | `[[框架]]` | 软关联 |
| `sales_bws` / `formula_ews` | `[[窗口识别]]` | 软关联 |
| `formula_gap_effect` | `[[情绪落差（GapEffect）]]` | 软关联 |
| `sales_pv` / `formula_is` / `formula_eev` / `formula_cs` / `sales_action` / `formula_action` | — | 无对应条目，未标注 |

> **不存在的 Wiki 条目直接不标**，不写"待补充"。Wiki 补齐后再补标注。

## 核心文件

| 文件 | 功能 | 公式数量 |
|------|------|---------|
| `engine/formulas.py` | 公式基类（`_validate_params` 等工具函数） | 0（基础设施） |
| `engine/formulas_love.py` | 通用战态公式（chat-skills 遗产，跨项目共享） | 9 个 |
| `engine/formulas_sales.py` | 销售专属公式 | 6 个 |

**总计 15 个公式**：9 通用战态（IVI/SPE/EWS/IS/Gap_Effect/EEV/CS/action/params）+ 6 销售专属（BQ/BSP/BWS/PV/sales_action/sales_params）。

## 工作流程

公式分两步：自动参数 + 手动参数。Agent 先调 `sales_params` 获取可自动计算的值，再根据聊天内容判断手动参数，最后代入公式。

```python
from engine.tools import sales_params, sales_bq, sales_bsp, sales_bws, sales_action

# 第一步：自动参数
params = sales_params("张三")
# → {auto: {Sp, Fback, Rlatency, ...}, manual: {Pface, Ddepth, ...}}

# 第二步：Agent 判断 manual 参数
# 第三步：代入公式（核验视角，不机械套阈值）
bq = sales_bq(sp=0.7, fback=0.8, user_investment=0.3, pface=0.4)
bsp = sales_bsp(user_ddepth=0.6, target_ddepth=0.5, target_latency=1.2, user_latency=0.8)
bws = sales_bws(gap_effect=0.3, cp_index=0.5, eev=0.4, scarcity_loss=0.1)

# 第四步：辅助参考决策
action = sales_action(bq=bq["bq"], bsp=bsp["bsp"], bws=bws["bws"])
# → {"action": "bargain" / "push" / "nurture" / "reset" / "maintain"}
```

> **重要**：`action` 结果仅作参考视角。最终决策由 Agent 基于 Wiki 知识 + 事实档案 + 实时数据综合判断。

## 销售专属公式（formulas_sales.py，6 个）

### BQ（购买意愿真实度）

```
BQ = Sp × 0.3 + Fback × 0.2 + User_Investment × 0.3 + (1 - Pface) × 0.2
```

| 参数 | 含义 | 来源 |
|------|------|------|
| `Sp` | 显示性偏好（客户对产品有兴趣的信号强度） | auto：qscore_personal × 1.5 + fback_quality × 0.3 |
| `Fback` | 回复字数比（客户/销售） | auto：fback.normalized |
| `User_Investment` | 我方投入程度 | auto：1.0 - neediness_penalty |
| `Pface` | 面子阻力（客户维持形象的防备程度） | **manual**：0.1-0.9 |

**参考阈值**（非硬规则）：>1.0 真实意向，<0.5 真实没戏
**Wiki 依据**：`[[购买意向指标]]`

### BSP（商务势能）

```
BSP = (User_Ddepth / Target_Ddepth) × (Target_Latency / User_Latency)
```

| 参数 | 含义 | 来源 |
|------|------|------|
| `User_Ddepth` | 销售的急迫程度 | **manual**：0.1-0.9 |
| `Target_Ddepth` | 客户的紧迫程度 | **manual**：0.1-0.9 |
| `Target_Latency` | 客户的回复延迟 | auto：rlatency 反推 |
| `User_Latency` | 销售的回复延迟 | auto：rlatency 推导 |

**参考阈值**（非硬规则）：0.8-1.5 健康，<0.6 红线阻断
**Wiki 依据**：`[[框架]]`

### BWS（购买窗口期）

```
BWS = (Gap_Effect × Cp_Index) + EEV - Scarcity_Loss
```

| 参数 | 含义 | 来源 |
|------|------|------|
| `Gap_Effect` | 情绪落差（Act - Exp） | auto |
| `Cp_Index` | 配合度指数（客户对微小指令的顺从程度） | **manual**：0.0-1.0 |
| `EEV` | 成交期望值 | auto |
| `Scarcity_Loss` | 稀缺性损耗 | auto：消息量趋势+延迟趋势 |

**参考阈值**（非硬规则）：>0.8 出击信号，<0.3 窗口关闭
**Wiki 依据**：`[[窗口识别]]`

### PV（成交期望值）

```
PV = P_succ × escalation_bonus - P_fail × loss_risk
```

| 参数 | 含义 | 来源 |
|------|------|------|
| `P_succ` | 成交成功概率 | **manual**：0.0-1.0 |
| `escalation_bonus` | 推进收益 | **manual** |
| `P_fail` | 失败概率 | **manual**：0.0-1.0 |
| `loss_risk` | 失败代价 | **manual** |

**参考阈值**（非硬规则）：>0.3 值得推进
**Wiki 依据**：无（Wiki 待补齐）

### sales_action（销售行动决策）

```python
def sales_action(bq, bsp, bws, bs=0.0, pv=0.5) -> dict:
    """辅助参考决策。返回 {"action": "...", "reason": "...", "instructions": [...]}。"""
```

| 条件 | 决策 |
|------|------|
| BQ > 1.0 且 BWS > 0.8 且 PV > 0.3 | **bargain**（报价/逼单） |
| BQ > 0.7 且 BSP >= 0.6 | **push**（推进） |
| BS > 0 且 BWS > 0.5 | **nurture**（培育） |
| BQ < 0.5 或 BSP < 0.6 | **reset**（重置关系） |
| 其他 | **maintain**（维持） |

## 通用战态公式（formulas_love.py，9 个）

跨项目共享的 chat-skills 遗产公式，在 SalesCRM 中作为辅助参考。

| 公式 | 含义 | Wiki 依据 |
|------|------|-----------|
| `formula_ivi` | 意图真实度指数 | `[[购买意向指标]]` |
| `formula_spe` | 社交势能指数 | `[[框架]]` |
| `formula_ews` | 推进窗口期 | `[[窗口识别]]` |
| `formula_is` | 真实需求度 | 无 |
| `formula_gap_effect` | 情绪落差刺激 | `[[情绪落差（GapEffect）]]` |
| `formula_eev` | 推进期望值 | 无 |
| `formula_cs` | 矛盾状态 | 无 |
| `formula_action` | 综合策略分发 | 无 |
| `formula_params` | 自动参数计算 | 无（参数函数） |

公式签名和阈值参考 `engine/formulas_love.py` docstring。

## 自动参数推导

`sales_params(name)` / `formula_params(name)` 从数据库指标推导以下 auto 参数：

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

## 数据流

```
tools.py: sales_params('张三')
    ↓
formulas_sales.py: 自动连接 DB → compute_metrics_for_contact → 推导 auto 参数
    ↓
返回 {auto: {...}, manual: {Pface: {hint, range, default}, ...}}

Agent 根据聊天内容判断 manual 参数值
    ↓
sales_bq(sp, fback, user_investment, pface)
    ↓
返回 {"bq": 1.23, "interpretation": "真实意向", ...}
    ↓
Agent 结合 Wiki[[购买意向指标]] 核验结果，做最终判断
```

## BQ 核验示例：如何通过 Wiki 条目核验公式结果

以 BQ 公式为例，展示 Agent 如何结合 Wiki 条目核验公式输出（参考 [example_analysis_sales.md](../../exchange/architecture/example_analysis_sales.md) 的分析风格）。

**场景**：客户张三，调 `sales_bq(sp=0.7, fback=0.8, user_investment=0.3, pface=0.4)` 返回 `bq=1.23`，公式 interpretation = "真实意向"。

**核验步骤**：

1. **查公式结果**：BQ=1.23，公式判定"真实意向"（行为投入远超表面）
2. **查 Wiki 条目**：`wiki_search("购买意向指标")` → 返回 `[[购买意向指标]]` 全文
3. **逐项对照核验**：

| 公式分量 | 值 | Wiki 条目说法 | 一致性 |
|---------|-----|-------------|--------|
| Sp（显示性偏好） | 0.7（高） | "客户主动询问产品细节是真实意向信号" | ✓ 一致 |
| Fback（回复字数比） | 0.8（高） | "回复速度和字数变化反映意向波动" | ✓ 一致 |
| User_Investment（我方投入） | 0.3（低） | "销售方过度投入会压低真实意向信号" | ✓ 一致（我方投入低反而拉高 BQ） |
| Pface（面子阻力） | 0.4（中） | "客户防备心强时口头表态不可信" | ✓ 一致（BQ>1.0 说明行为>表态） |

4. **综合判断**：Wiki 框架与公式结果一致，Agent 可采信"真实意向"判断。但最终决策仍需结合事实档案（`evidence`）和实时数据（`brief`/`chat`）。

**反例（核验不一致时）**：

- 若 Wiki 条目说"短期高频回复不等于真实意向（可能是客套或信息收集）"，而公式 BQ=1.23 判定"真实意向"
- Agent 应采信 Wiki 框架，将公式结果标记为"待核验"，**不直接采信公式判断**
- 在分析输出中显式记录："公式判定真实意向，但 Wiki[[购买意向指标]]提示短期高频不可信，需观察 2 周后再判断"

**核心原则**：公式是辅助参考视角，Wiki 是推理主轴。当两者冲突时，以 Wiki 框架为准，公式结果降级为"待核验"。

## 注意事项

1. **公式是辅助参考**：公式结果仅作量化视角参考，不主导决策。最终判断由 Agent 基于 Wiki + 事实档案 + 实时数据综合得出。
2. **阈值是参考，不是硬规则**：BQ=0.9 不一定比 BQ=1.1 差，要结合上下文和 Wiki 框架判断。
3. **manual 参数是关键**：auto 参数只提供基础数据，真正区分分析质量的是 Agent 对 Pface/Ddepth/Backstage 的判断。
4. **公式来自 chat-skills 遗产**：原项目已删除，公式提取到此处并适配销售场景。与 SalesCRM Wiki 知识库是**软关联**关系（通过标注 Wiki 依据条目），不是派生关系。详见"目标 vs 现状"表。
5. **参数校验**：所有公式函数对参数做类型校验（必须是数字），非数字参数会返回错误消息而非抛异常。
6. **`sales_params` 可接受外部连接**：默认自己开 DB 连接，也支持 `conn` 参数传入，避免重复连接。
