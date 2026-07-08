# 分析工作流 — 完整流程 + 决策树 + 报告模板

## 核心原则：Wiki 贯穿全程

Wiki 不是"第二步做完就不管了"的参考材料。它是推理主轴，在分析过程的每个环节都应随时查阅：
- 看到 brief 信号 → 查 Wiki 理解信号含义
- 看到聊天模式 → 查 Wiki 找话术和互动策略
- 看到指标数据 → 查 Wiki 解读指标背后的含义
- 看到关系阶段 → 查 Wiki 找阶段策略
- 写报告时 → 查 Wiki 引用具体条目作为策略依据

---

## 完整分析流程

### 第零步（必须）：同步最新消息 — 【MCP工具】`person_sync(name)`
不同步看到的是旧数据，可能遗漏最近聊天。耗时几秒。同步失败不阻塞分析。

**下一步**：`person_brief` 获取全局视图

⚠️ 联系人搜不到（PERSON_NOT_FOUND）时：
1. `system_sync(meta_only=True)` → 同步联系人列表（约 1 秒）
2. `contact_search(query)` → 搜索联系人
3. 找到了 → `person_sync(name)` 同步消息后继续
4. 还是没找到 → 告诉用户"微信里没有和这个客户的聊天记录"

### 第一步：获取全局视图 + 初次 Wiki 查询 — 【MCP工具】`person_brief(name)`
1. `person_brief(name)` → 结构化数据：身份信息、指标、事件、信号、Wiki 推荐
2. 看到 brief 中的信号后，立即查 Wiki 建立方法论框架：
   - `wiki_search("关键词")` → 搜索
   - `wiki_read("路径")` → 读取具体页面全文

**下一步**：`wiki_search` 建立方法论框架

常用 Wiki 框架速查：
| 信号 | 推荐搜索词 |
|------|-----------|
| 客户有兴趣 | 购买意向指标 需求确认 |
| 回复变慢 | 频率法则 需求感 |
| 会面 | 从线上到第一次拜访 |
| 忽冷忽热 | 需求刺激 情绪波动 |
| 成交时机 | 成交窗口 逼单时机 |

### 第二步：详细数据 + 持续 Wiki 查询
逐步获取数据，每看到新信息就查 Wiki 解读：

1. `person_chat(name, recent=200)` 【MCP工具】→ 聊天记录
   → 看到聊天模式后：`wiki_search("话题技巧"/"需求刺激"/"冷读")`
2. `person_metrics(name)` 【MCP工具】→ 指标数据
   → 看到具体数值后：`wiki_search("频率法则"/"需求感"/"购买意向")`
3. `person_signals(name)` 【MCP工具】→ 信号详情
   → 看到信号类型后：`wiki_read` 读取对应框架全文
4. `person_timeline(name)` 【MCP工具】→ 关系时间线
   → 看到趋势后：`wiki_search("趋势分析"/"降温"/"窗口期")`
5. `person_evidence(name)` 【MCP工具】→ 事实档案
   → 对比历史事实与 Wiki 框架
6. `person_moments_stats(name)` 【MCP工具】→ 朋友圈互动
   → `wiki_search("展示面"/"朋友圈"/"社交认证")`

### 第三步：公式核验 + Wiki 交叉验证
- `formula_get_params(name)` 【MCP工具】→ 获取战态公式自动参数
- `formula_calc_ivi(...)` / `formula_calc_spe(...)` / `formula_calc_ews(...)` 【MCP工具】→ 战态分析量化视角
- `sales_get_params(name)` 【MCP工具】→ 获取销售公式参数
- `sales_calc_bq(...)` / `sales_calc_bsp(...)` / `sales_calc_bws(...)` 【MCP工具】→ 销售决策量化视角

**下一步**：用 `wiki_search` 核验公式结果

⚠️ 公式数值只在"数据全貌"表出现一次，策略全部回指 Wiki 条目
⚠️ 不机械套阈值。BQ=0.5 不一定比 BQ=1.1 差，结合 Wiki 判断
→ 公式结果与 Wiki 矛盾时？以 Wiki 为准，公式仅作参考

### 第四步（必须）：保存分析报告 — 【MCP工具】`save_from_markdown(name, markdown_text)`
1. 【必须】`save_from_markdown(name, markdown_text)` → 写入 latest.md + latest.yaml
2. 【可选】`person_save_analysis(name, stage=..., confidence=..., ...)` → 补充结构化字段

---

## 决策树：用户想要什么 → 怎么做

### 场景 1：分析某个客户的关系
```
用户说"帮我分析XX" / "XX的情况" / "看看XX"
  ├─ person_sync("XX")          # 【必须】同步 【MCP工具】
  ├─ person_brief("XX")         # 全局视图 【MCP工具】
  ├─ wiki_search(信号关键词)     # 读 Wiki 框架 【MCP工具】
  ├─ person_chat("XX", recent=200)  # 【可选】看聊天 【MCP工具】
  ├─ person_evidence("XX")      # 【可选】追溯事实 【MCP工具】
  ├─ person_metrics/signals     # 指标+信号 【MCP工具】
  ├─ formula_calc_* / sales_calc_*  # 【可选】公式核验 【MCP工具】
  └─ save_from_markdown("XX", 报告)  # 【必须】保存 【MCP工具】
```

### 场景 2：紧急回复
```
用户说"客户发了XX怎么回" / "怎么回复"
  ├─ person_sync("XX") 【MCP工具】
  ├─ person_chat("XX", recent=30) 【MCP工具】
  ├─ person_metrics("XX") 【MCP工具】
  ├─ wiki_search("需求刺激 冷读 逼单") 【MCP工具】
  └─ 给出：一条可直接发送的推荐回复 + 备选 + 不要说 + 观察点
```

### 场景 3：会面前
```
用户说"会面前" / "客户说了XX了怎么办"
  ├─ person_brief("XX") 【MCP工具】
  ├─ wiki_search("第一次拜访 需求挖掘") 【MCP工具】
  └─ 即时建议：简短、可执行、不要长篇大论
```

### 场景 4：搜索知识
```
用户说"怎么逼单" / "什么是BQ" / "帮我搜一下XX"
  ├─ wiki_search("关键词") 【MCP工具】
  ├─ wiki_read("路径") 【MCP工具】
  └─ 结合知识内容回答
```

### 场景 5：开放求助
```
用户说"我该怎么办" / "客户最近忽冷忽热" / "要不要放弃"
  ├─ person_sync("XX") 【MCP工具】
  ├─ person_brief("XX") 【MCP工具】
  ├─ wiki_search("忽冷忽热") 【MCP工具】
  └─ 深度分析 + 策略 + 风险
```

### 场景 6：客户画像
```
用户说"帮我画像XX" / "XX是什么类型"
  ├─ person_sync("XX") 【MCP工具】
  ├─ person_chat("XX", recent=200) 【MCP工具】
  ├─ person_evidence("XX") 【MCP工具】
  ├─ wiki_search("客户心理 决策风格") 【MCP工具】
  └─ 画像 + 沟通指南 + 话术建议
```

### 场景 7：记录信息
```
用户说"帮我记一下XX" / "XX说了XX"
  ├─ person_note("XX", "内容") 【MCP工具】
  ├─ person_date_record("XX", date_text="2026-06-08", location="客户公司", rating=4) 【MCP工具】
  ├─ person_evaluate("XX", "评估内容") 【MCP工具】
  └─ events_save("XX")  # 检测并写入事件 【MCP工具】
```

### 场景 8：周报
```
用户说"做一下周报" / "本周排名"
  ├─ system_sync()  # 全局同步（不是 person_sync）【MCP工具】
  └─ weekly_report() 【MCP工具】
```

### 场景 9：挽回 / 冷激活
```
用户说"客户不理我了" / "想挽回"
  ├─ person_sync("XX") 【MCP工具】
  ├─ person_brief("XX")  # 看断联时间+信号 【MCP工具】
  ├─ wiki_search("挽回 冷激活 断联") 【MCP工具】
  └─ 判断类型后给方案
```

---

## 时间线感知

拿到聊天记录分析时，**第一件事梳理时间线**：
- 回复间隔：秒回还是几小时？有没有变化趋势？
- 主动 vs 被动：谁先发的？哪段是客户主动？
- 密集 vs 冷淡：哪段热？哪段降温？降温前发生了什么？
- 最后一条：谁发的？多久没动静了？
- 整体趋势：升温还是降温？

时间维度直接影响建议：客户连续 3 小时秒回然后突然不回 ≠ 客户一直慢回。

---

## 分析报告模板（8 段式深度报告）

⚠️ 这不是简短摘要，而是详细分析报告。每段必须有实质内容。
⚠️ 策略段必须引用 Wiki 条目（[[条目名]] 格式）。

```markdown
# {显示名} 客户分析报告

> 分析日期：{YYYY-MM-DD}
> 数据来源：MCP 工具链（person_brief/metrics/stage/signals/timeline/chat）
> 知识库参考：{列出本次引用的 Wiki 条目}

## 一、场景理解（至少 3-5 句叙事）
- 当前关系阶段、互动周期、核心问题
- 用叙事方式描述情境
- 格式：阶段（置信度 XX%）+ 详细情境描述

## 二、数据全貌（表格，Wiki 解读列不能为空）
| 维度 | 数值 | Wiki 解读 |
|------|------|----------|
| 综合指数 | composite | [[购买窗口识别]] — 信号等级 |
| 回复字数比 | fback | [[购买意向指标]] — 字数比反映兴趣 |
| 回复速度 | rlatency | [[频率法则]] |
| 聊天质量 | fback_quality | [[需求感控制]] |
| 个人化问题 | qscore_personal | [[意向判断]] |
| 趋势变化 | trend | [[购买窗口识别]] |
| 情绪波动 | escore_volatility | [[情绪波动技术]] |
| 朋友圈互动 | moments | [[展示面建设]] |
| 饥饿感 | msg_volume_trend | [[需求刺激]] |
| 最后联系 | recent | — |

公式参考（辅助视角）：战态 IVI={} SPE={} EWS={} / 销售 BQ={} BSP={} BWS={} PV={}
→ 这些数值不主导策略，策略依据见下方 Wiki 诊断

## 三、关键信号分析（分积极/消极）
### 积极信号
| 信号 | 具体表现 | Wiki 来源 |
|------|---------|----------|
| 例：主动咨询 | 客户本周主动问了3次产品 | [[购买意向指标]] |

### 消极信号
| 信号 | 具体表现 | Wiki 来源 |
|------|---------|----------|
| 例：回复变慢 | 平均回复时延从2h升到8h | [[频率法则]] |

## 四、Wiki 框架诊断（至少引用 3 个 Wiki 条目）
- 用多个 Wiki 条目交叉分析
- 每个条目先简述框架核心观点，再对照本案例数据
- 区分事实（客户说了什么）和推断（可能什么意思）

## 五、具体操作（分阶段，每步引用 Wiki，含话术示例）
### 第一阶段（如：线上互动调整）
| 客户的行为 | 信号 | 你该做什么 | Wiki 依据 |
|---------|------|-----------|----------|
| 例：问价格 | 需求钩子 | 不直接报价，先挖掘需求 | [[需求刺激]] |

### 第二阶段（如：推进会面）
- 具体邀约话术示例

## 六、绝对不要做（每条有 Wiki 依据）
| ❌ 不要做 | 原因 | Wiki 依据 |
|----------|------|----------|
| 例：秒回每条消息 | 暴露需求感 | [[需求感控制]] |

## 七、核心风险
| 风险 | 概率 | 说明 | 应对 |
|------|------|------|------|
| 例：客户流失 | 高 | 回复时延持续上升 | [[客户流失预警]] |

## 八、底层判断
- 对当前客户关系本质的判断
- 用 **加粗** 标注关键结论
- 回指 Wiki 框架作为判断依据
```
