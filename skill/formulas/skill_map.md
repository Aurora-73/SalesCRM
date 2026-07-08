---
name: formula-skill-map
description: 公式与Skill的映射关系 — 每个公式对应哪个Wiki框架
---

# 公式-Skill 映射

## 映射总览

### 战态公式

| 公式 | Wiki依据 | Skill参考 | 下一步建议 |
|------|----------|-----------|-----------|
| formula_calc_ivi | [[IOI（兴趣指标）]] | `signals/basic_signals.md` | `wiki_search("IOI")` |
| formula_calc_spe | [[框架（Frame）]] | `signals/basic_signals.md` | `wiki_search("框架")` |
| formula_calc_ews | [[窗口识别]] | `workflows/analysis.md` | `wiki_search("窗口")` |
| formula_calc_is | [[亲密度]] | `signals/basic_signals.md` | `wiki_search("亲密")` |
| formula_calc_gap_effect | [[情绪波动]] | `signals/basic_signals.md` | `wiki_search("情绪")` |
| formula_calc_eev | [[行动决策]] | `workflows/analysis.md` | `wiki_search("决策")` |
| formula_calc_cs | [[矛盾]] | `signals/basic_signals.md` | `wiki_search("矛盾")` |
| formula_calc_action | [[行动决策]] | `workflows/analysis.md` | `wiki_search("行动")` |

### 销售公式

| 公式 | Wiki依据 | Skill参考 | 下一步建议 |
|------|----------|-----------|-----------|
| sales_calc_bq | [[购买意向指标]] | `signals/basic_signals.md` | `wiki_search("购买意向")` |
| sales_calc_bsp | [[框架]] | `signals/basic_signals.md` | `wiki_search("框架")` |
| sales_calc_bws | [[窗口识别]] | `workflows/analysis.md` | `wiki_search("窗口")` |
| sales_calc_pv | — | `signals/sales_signals.md` | `wiki_search("成交")` |
| sales_calc_action | [[行动决策]] | `workflows/analysis.md` | `wiki_search("行动")` |

---

## 使用流程

```
1. formula_get_params(name)     # 获取战态公式参数
2. sales_get_params(name)       # 获取销售公式参数
3. formula_calc_ivi(...)        # 计算战态公式
4. sales_calc_bq(...)           # 计算销售公式
5. wiki_search("购买意向")      # 根据公式结果查Wiki
6. wiki_read("...")             # 读取Wiki全文
7. 结合Wiki知识判断              # 不机械套用公式阈值
```

---

## 公式核验示例

**场景**：`sales_calc_bq` 返回 BQ=0.5（中性区间）

**错误做法**：
```
BQ=0.5 < 1.0 → "无意向" → 放弃跟进
```

**正确做法**：
```
1. 查 Wiki [[购买意向指标]]
2. 看聊天记录：客户最近3次主动询问产品细节
3. 看指标：回复速度快，回复质量高
4. 判断：虽然BQ中等，但实际是购买意向信号
```

---

## 冲突裁决

当公式结果与 Wiki 知识矛盾时：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | Wiki 知识 | 方法论框架，推理主轴 |
| 2 | 实时数据 | 当前事实，不可推翻 |
| 3 | 事实档案 | 客观记录，可信 |
| 4 | 公式计算 | 量化视角，辅助参考 |

**原则**：公式结果只能作为参考，不能推翻 Wiki 知识和实时数据。

---

## 销售场景特殊考虑

在 B2B 销售场景中，需要特别注意：

| 场景 | 公式提示 | 正确做法 |
|------|---------|---------|
| 客户长时间不回复 | recent 高，signal_level 低 | 不一定代表无意向，可能处于审批流程 |
| 客户询问竞对 | BQ 可能下降 | 正常销售流程，需做差异化定位 |
| 客户说"考虑一下" | BWS 下降 | 不一定是拒绝，需确认决策链和时间线 |
| 客户要求演示 | BQ 上升 | 是积极信号，但需确认预算和决策人 |