"""MCP guide 工具：提供使用指南和工作流文档。

Agent 通过 guide(topic) 获取操作指南，无需阅读外部文档即可正确使用系统。

内容维护：
- guide 内容是 readme/*.md 和 .claude/skills/*.md 的精简映射，后者是权威来源
- readme/skills 变更时必须检查是否影响 guide 内容
- 如果 readme 和 guide 矛盾，以 readme 为准
- 触发更新场景：新增MCP工具/新增Wiki页面/修改操作流程/修改输出规范/新增权限规则
"""

GUIDES: dict[str, str] = {
    "getting-started": """# SalesCRM MCP 快速入门

## 系统是什么
一个 AI 辅助的客户关系分析系统。通过微信聊天数据、Wiki 知识库和量化指标，帮助你分析客户状态、制定推进策略。

## 三件事你必须知道
1. ⚠️ **分析前先同步** — 每次分析某客户前先调 person_sync(name)，否则看到的是旧数据
2. ⚠️ **Wiki 贯穿全程** — 不是只读一次！看到信号→查Wiki，看到聊天→查Wiki，看到指标→查Wiki，写报告→引用Wiki
3. ⚠️ **分析完必须写报告** — 调 save_from_markdown 写完整报告，否则历史无法追溯

## 三个最常用场景

场景 A：分析某个客户
  guide("workflow/analysis") → 获取完整流程

场景 B：客户发了消息怎么回
  1. person_sync(name)
  2. person_chat(name, recent=30)
  3. person_metrics(name)
  4. wiki_search("关键词")
  5. 给出一条可直接发送的回复

场景 C：周报/排名
  1. system_sync()  → 全局同步（仅私聊，跳过群聊/公众号）
  2. weekly_report()

## 所有可用指南主题
- guide("workflow/analysis") → 客户分析完整流程
- guide("report-template") → 分析报告模板
- guide("methodology") → 核心方法论（Wiki 主轴、公式辅助、冲突裁决）
- guide("rules/evidence") → 事实档案写入规则
- guide("rules/permissions") → 操作权限规范
- guide("rules/reply") → 回复构造规则
- guide("workflow/maintain") → 客户维护工作流
- guide("reference/sync") → 同步策略速查
- guide("reference/formula") → 公式使用指南
- guide("reference/stickers") → 贴纸系统说明
""",
    "workflow/analysis": """# 客户分析完整流程

## 执行前提
WCD 后端必须在 http://127.0.0.1:10392 运行。
- 调 wcd_status() 检查后端状态
- 如果 offline → 调 wcd_start() 启动后端（等待健康检查通过）
- 如果 online → 继续下一步

## ⚠️ 核心原则：Wiki 贯穿全程，不是一次性步骤
Wiki 不是"第二步做完就不管了"的参考材料。它是推理主轴，在分析过程的每个环节都应随时查阅：
- 看到 brief 信号 → 查 Wiki 理解信号含义
- 看到聊天模式 → 查 Wiki 找话术和互动策略
- 看到指标数据 → 查 Wiki 解读指标背后的含义
- 看到关系阶段 → 查 Wiki 找阶段策略
- 写报告时 → 查 Wiki 引用具体条目作为策略依据

## 第零步（必须）：同步最新消息
调 person_sync(name)
- 不同步 = 看到的是上次同步时的旧数据，可能遗漏最近的聊天
- 耗时一般几秒
- 同步失败不阻塞分析，用旧数据继续

⚠️ 如果联系人搜不到（PERSON_NOT_FOUND）：
  1. 调 system_sync(meta_only=True) → 同步联系人列表（约 1 秒）
  2. 调 contact_search(query) → 搜索联系人
  3. 找到了？→ 调 person_sync(name) 同步消息后继续
  4. 还是没找到？→ 告诉用户"微信里没有和这个客户的聊天记录"

## 第一步：获取全局视图 + 初次 Wiki 查询
1. 调 person_brief(name)
   → 返回结构化数据：身份信息、数据可信度、composite 指标、事件列表、信号检测、Wiki 推荐

2. 看到 brief 中的信号后，立即查 Wiki 建立方法论框架：
   - 调 wiki_search("关键词") → 搜索，如 wiki_search("购买意向 需求确认 成交")
   - 调 wiki_read("路径") → 读取具体页面的全文

常用 Wiki 框架速查：
| 信号 | 推荐搜索词 |
|------|-----------|
| 客户有兴趣 | 购买意向指标 需求确认 |
| 回复变慢 | 频率法则 需求感 |
| 会面 | 从线上到第一次拜访 |
| 忽冷忽热 | 需求刺激 情绪波动 |
| 成交时机 | 成交窗口 逼单时机 |

## 第二步：详细数据 + 持续 Wiki 查询
逐步获取数据，每看到新信息就查 Wiki 解读：

1. person_chat(name, recent=200) → 聊天记录
   → 看到聊天模式后：wiki_search("话题技巧"/"需求刺激"/"冷读") 查话术策略

2. person_metrics(name) → 指标数据
   → 看到具体数值后：wiki_search("频率法则"/"需求感"/"购买意向") 解读指标含义

3. person_signals(name) → 信号详情
   → 看到信号类型后：wiki_read 读取对应信号框架的全文

4. person_stage(name) → 关系阶段
   → 看到阶段后：wiki_search("阶段策略"/"升温"/"推进") 查阶段策略

5. person_timeline(name) → 关系时间线
   → 看到趋势后：wiki_search("趋势分析"/"降温"/"窗口期") 理解趋势

6. person_evidence(name) → 事实档案
   → 对比历史事实与 Wiki 框架，判断当前状态

7. person_moments_stats(name) → 朋友圈互动
   → wiki_search("展示面"/"朋友圈"/"社交认证") 理解社交信号

## 第三步：公式核验 + Wiki 交叉验证
调 formula_get_params(name) → 获取战态公式自动参数
调 formula_calc_ivi/spe/ews/action(...) → 获取战态分析量化视角
调 sales_get_params(name) → 获取销售公式参数
调 sales_calc_bq/bsp/bws/pv/action(...) → 获取销售决策量化视角

⚠️ 公式数值只在"数据全貌"表出现一次，策略全部回指 Wiki 条目
⚠️ 不机械套阈值。BQ=0.5 不一定比 BQ=1.1 差，结合 Wiki 判断
→ 公式结果与 Wiki 框架矛盾时？以 Wiki 为准，公式仅作参考视角

## 第四步（必须）：保存分析报告
1. 【必须】调 save_from_markdown(name, markdown_text)
   → 写入完整 Markdown 报告到 data/outputs/analysis/<name>/latest.md
   → 报告模板见 guide("report-template")
   → 报告中的策略必须引用 Wiki 条目（[[条目名]] 格式）

2. 【推荐】调 person_save_analysis(name, stage=..., confidence=..., ...)
   → 写入结构化 YAML 到 latest.yaml，支持后续 person_compare 对比
   → 参数：stage（阶段）/ confidence（置信度）/ reasoning（推理）/ diagnosis（诊断）/ strategy（策略）/ risks（风险列表）
   → evidence_refs 可以把关键消息 ID 写入 YAML 形成证据链

不保存的后果：历史分析无法追溯、brief 不显示历史分析、personal_patterns 无法累积
""",
    "report-template": """# 分析报告模板（8 段式深度报告）

⚠️ 这不是一份简短摘要，而是一份详细的分析报告。
⚠️ 每一段都必须有实质内容，不能只列公式数值和一句话结论。
⚠️ 策略段必须引用 Wiki 条目（[[条目名]] 格式），不能只写"减少联系频率"。
⚠ 参考 exchange/architecture/example_analysis_sales.md 的深度和风格。

## 格式

# {显示名} 客户分析报告

> 分析日期：{YYYY-MM-DD}
> 数据来源：MCP 工具链（person_brief/metrics/stage/signals/timeline/chat）
> 知识库参考：{列出本次分析引用的所有 Wiki 条目}

## 一、场景理解（至少 3-5 句叙事，不是一句话）
- 当前关系阶段、互动周期、核心问题
- 用叙事方式描述情境（客户最近在做什么、你们之间的互动模式）
- 引用 Wiki 框架解释当前情境（如 [[购买窗口识别]]、[[关系三要素]]）
- 格式：阶段（置信度 XX%）+ 详细情境描述

## 二、数据全貌（必须用表格，Wiki 解读列不能为空）
| 维度 | 数值 | Wiki 解读 |
|------|------|----------|
| 综合指数 | composite | [[购买意向判断]] — 信号等级说明 |
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

## 三、关键信号分析（必须分积极/消极，每个信号引用 Wiki）
### 积极信号（购买意向）
| 信号 | 具体表现 | Wiki 来源 |
|------|---------|----------|
| 例：主动咨询 | 客户本周主动问了 3 次产品 | [[购买意向指标]] |

### 消极信号
| 信号 | 具体表现 | Wiki 来源 |
|------|---------|----------|
| 例：回复变慢 | 平均回复时延从 2h 升到 8h | [[频率法则]] |

## 四、Wiki 框架诊断（至少引用 3 个 Wiki 条目交叉验证）
- 用多个 Wiki 条目交叉分析当前状态（不依赖单一框架）
- 每个条目先简述框架核心观点，再对照本案例数据
- 区分事实（客户说了什么）和推断（可能什么意思）
- 示例：[[需求确认]] 框架下，客户的 X 行为暗示...

## 五、具体操作（分阶段，每步引用 Wiki，含话术示例）
### 目标设定
- 本次操作的核心目标

### 第一阶段（如：线上互动调整）
| 客户的行为 | 信号 | 你该做什么 | Wiki 依据 |
|---------|------|-----------|----------|
| 例：问价格 | 需求钩子 | 不直接报价，先挖掘需求 | [[需求刺激]] |

### 第二阶段（如：推进会面）
- 具体邀约话术示例

## 六、绝对不要做（每条必须有 Wiki 依据）
| ❌ 不要做 | 原因 | Wiki 依据 |
|----------|------|----------|
| 例：秒回每条消息 | 暴露需求感 | [[需求感控制]] |

## 七、核心风险
| 风险 | 概率 | 说明 | 应对 |
|------|------|------|------|
| 例：客户流失 | 高 | 回复时延持续上升 | [[客户流失预警]] |

## 八、底层判断（本质判断，回指 Wiki 框架）
- 对当前客户关系本质的判断（不引用数据，只讲判断）
- 用 **加粗** 标注关键结论
- 回指 Wiki 框架作为判断依据

## 使用说明
1. 分析过程中持续查 Wiki（不是最后才查）
2. 把上述模板填入实际数据，每段都要有实质内容
3. 调 save_from_markdown(name, 填入后模板) 保存 — 会同时生成 .md 和 .yaml 两个文件
4. 可选：调 person_save_analysis(name, ...) 补充结构化字段
""",
    "methodology": """# 核心方法论

## Wiki 是推理主轴（贯穿全程，不是一次性步骤）
- Wiki 不是"参考资料"，是分析方法论的来源
- Wiki 不是"第二步做完就不管了"——在分析过程的每个环节都应随时查阅
- 使用 wiki_search("关键词") 搜索，wiki_read("路径") 读全文

Wiki 查询时机：
- 看到 brief 信号 → 查 Wiki 理解信号含义
- 看到聊天模式 → 查 Wiki 找话术和互动策略
- 看到指标数据 → 查 Wiki 解读指标背后的含义
- 看到关系阶段 → 查 Wiki 找阶段策略
- 看到公式结果 → 查 Wiki 核验而非套阈值
- 写报告时 → 查 Wiki 引用具体条目作为策略依据

## 公式是辅助参考（核验而非套用）
- 公式数值在"数据全貌"表中出现一次
- 后续所有策略判断必须引用 Wiki 条目，不引用公式数值
- BQ=0.5 不一定比 BQ=1.1 差——结合 Wiki 知识核验
- 公式是"视角"不是"裁判"

## 冲突裁决规则
当不同数据源矛盾时，按以下优先级裁决：
| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1（最高） | 实时数据（brief/chat/metrics） | 当前事实，不可推翻 |
| 2 | 事实档案（evidence: note/date/events） | 客观记录，可信 |
| 3 | 事件检测（events） | 从数据推导，基本可信 |
| 4 | 公式计算（formula_* / sales_*） | 量化视角，有启发但需核验 |
| 5（最低） | 历史分析（data/outputs/analysis/） | 过去的观点，可能已过时 |

## 分析六段式
1. 场景理解 — 先理解情境再分析
2. 数据全貌 — 配 Wiki 解读列，公式数值出现一次
3. Wiki 框架诊断 — 用多个 Wiki 条目交叉验证
4. 具体操作 — 每步引用 Wiki 依据
5. 绝对不要做 — 列出禁忌及其 Wiki 依据
6. 底层判断 — 本质判断，回指 Wiki 框架
""",
    "rules/evidence": """# 事实档案写入规则

## 概念分层
| 层 | 内容 | 工具 | 冲突优先级 |
|---|------|------|-----------|
| 事实档案 | 客观事实 | note / date / events | 2（高） |
| 分析归档 | 主观判断 | evaluate / save_analysis | 5（最低） |

## 自检三问（写入 person_note 前必答）
1. 这条信息是客户说的/做的，还是我推断的？→ 只能写前者
2. 如果换一个 Agent 读这条信息，会得出同样的结论吗？→ 如果不会，说明掺杂了判断
3. 这条信息 3 个月后还有效吗？→ 事实是稳定的，判断会过时

## 可以写 vs 不可以写
| ✅ 可以写（客观事实） | ❌ 不可写（主观判断） |
|---------------------|---------------------|
| 客户原话："我们预算大概 50 万" | "客户对我们有好感，值得追" |
| 客户行为："凌晨主动发消息确认方案" | "客户肯定想买" |
| 用户补充："上次拜访客户很满意" | "本月成交成功率 80%" |
| 事件记录："6/1-6/15 断联 15 天" | "客户已经不感兴趣了" |

## 特殊说明
person_evaluate 虽然写入事实档案文件，但概念上属于分析归档。
Agent 读取 person_evidence 时，对 evaluations 段落要保持批判性，
不能将其与 notes/events/dates 等客观事实同等对待。
""",
    "rules/permissions": """# 操作权限规范

| 类型 | 工具 | 是否需要确认 | 说明 |
|------|------|------------|------|
| 只读 | brief/chat/metrics/status/rank/wiki/* | ❌ 不需要 | 自由调用 |
| 追加写入 | note/date/evaluate | ❌ 不需要 | 直接执行 |
| 覆盖写入 | save_analysis / save_from_markdown | ⚠️ 覆盖前告知 | save_from_markdown 是必做，save_analysis 可选 |
| 检测写入 | events_save | ⚠️ 先 scan 展示 | 先 events_scan 再 events_save |
| 不可逆 | contact_merge | 🔴 必须确认 | merge 不可撤销 |
""",
    "rules/reply": """# 回复构造规则

## 核心原则
1. 对话领导原则：浅话题（天气/吃的/在干嘛）必须 pivot 到需求/痛点/价值
2. 每次回复必须有一条可直接发送的消息草稿
3. 话术必须 context-consistent（不编造不存在的叙事）
4. 时间线感知：分析聊天时第一件事梳理时间线
5. 软抗拒 + 正面信号时坚持推进框架

## 时间线梳理要点
- 回复间隔：秒回还是几小时？有没有变化趋势？
- 主动 vs 被动：谁先发的？哪段是客户主动？
- 密集 vs 冷淡：哪段热？哪段降温？降温前发生了什么？
- 最后一条：谁发的？多久没动静了？
- 整体趋势：升温还是降温？

## 话术规则
- 有 hooks：消息要能让客户有理由回复（问句/分享/价值点）
- 匹配阶段：初识轻松 / 高频沟通分享案例 / 意向确认推进报价
- 不超过 2 句：简短，不给压力
""",
    "workflow/maintain": """# 客户维护工作流

## 第一步：获取候选人
调 maintain_list(limit=10) → 获取需要主动联系的客户

候选人优先级（maintain_list 已内部排序）：
1. 热度下降（recent > 3 且 trend < -0.005）— 最优先
2. 窗口未推进（signal_level ≥ 弱窗口 且 1 < recent ≤ 3）
3. 高潜力未投入（neediness_penalty > 0.9 且 recent > 2）

## 第二步：获取上下文
对每个候选人：
- person_brief(name) → 全局视图
- person_chat(name, recent=30) → 最近聊天
- person_metrics(name) → 指标数据
- person_evidence(name, section="timeline") → 关系时间线

## 第三步：输出建议
每人输出一条具体可发送的消息，规则：
- context-consistent：基于实际聊天内容
- 有 hooks：能让客户有理由回复
- 匹配阶段：不超过 2 句话

输出格式参考：

### 1. {名字}（排名 #{N}，信号：{信号}，最后联系：{N} 天前）
- 关系状态：{简述}
- 上次聊天：{摘要}
- 建议消息："{具体话术}"
- 原理：{理由}
""",
    "reference/sync": """# 同步策略速查

## 三种同步场景
| 场景 | 工具 | 耗时 | 说明 |
|------|------|------|------|
| 分析个人 | person_sync(name) | 几秒 | 只同步该客户的最新消息 |
| 联系人找不到 | system_sync(meta_only=True) | 约 1 秒 | 只同步联系人/会话列表，不同步消息 |
| 周报/全局 | system_sync() | 几分钟 | 同步所有私聊的最新消息 |

## WCD 后端启动
同步前 WCD 后端必须在 http://127.0.0.1:10392 运行。
- wcd_status() → 检查后端状态（只读检测，不启动）
- wcd_start() → 启动后端进程并等待健康检查通过
- 如果 wcd_status 显示 offline → 调 wcd_start 启动
- 如果 wcd_status 显示 online → 可直接同步

## 重要限制
⚠️ system_sync() 只同步私聊（个人聊天），跳过群聊和公众号
⚠️ 同步失败不阻塞分析，用旧数据继续
""",
    "reference/formula": """# 公式使用指南

## 两套公式系统

SalesCRM 提供两套公式，均为辅助参考视角：

### 战态分析公式（通用）
| 公式 | 含义 | 阈值（参考，不硬套） |
|------|------|-------------------|
| IVI | 意图真实度 | >1.0 真实意向，<0.5 敷衍 |
| SPE | 社交势能 | 0.8-1.5 健康，<0.6 红线 |
| EWS | 推进窗口期 | >0.8 出击，<0.3 关闭 |
| IS | 真实合作度 | >0.5 高合作度 |
| Gap_Effect | 情绪落差 | >0 正向，<0 负向 |
| EEV | 推进期望值 | >0.3 值得出击 |
| CS | 矛盾状态 | >0 欲望占主导 |
| action | 终极决策 | 基于 IVI+SPE+EWS |

### 销售决策公式（SalesCRM 独有）
| 公式 | 含义 | 阈值（参考，不硬套） |
|------|------|-------------------|
| BQ | 购买意愿真实度 | >1.0 强烈信号，<0.5 敷衍 |
| BSP | 商务势能 | 0.8-1.5 健康，<0.6 高危低位 |
| BWS | 购买意向期 | >0.8 出击，<0.3 关闭 |
| PV | 成交期望值 | >0.3 值得推进 |
| sales_action | 销售行动决策 | bargain/push/nurture/reset/maintain |

## 用法步骤
1. 调 formula_get_params(name) → 获取战态公式自动参数
2. 调 sales_get_params(name) → 获取销售公式自动参数
3. 根据聊天内容判断 manual 参数（Pface/Ddepth/Backstage/Cp_Index）
4. 代入公式：formula_calc_ivi(...) / sales_calc_bq(...)
5. 核验而非套用：结果只做参考，最终判断依据 Wiki 知识

## BQ 核验示例
sales_calc_bq 返回 BQ=0.5（中性区间）
❌ 错误：BQ=0.5 < 0.5 → "敷衍" → "建议放弃"
✅ 正确：读 [[购买意向指标]] → 客户最近 3 次主动询问方案 → 回复率 0.8 → 判断"购买窗口开放"
""",
    "reference/stickers": """# 贴纸系统

## 贴纸的角色
贴纸是信号检测的一部分。客户的贴纸选择可以反映情绪和态度。

## 镜像检测
如果客户用了你用过的贴纸 → 正向信号
- 强镜像：多次使用你的专属贴纸
- 中镜像：偶尔使用
- 弱镜像：使用过但频率低

## 标注体系
| 维度 | 选项 |
|------|------|
| 情绪 | 友好 / 抗拒 / 中性 / 意向 |
| 内容类型 | 日常 / 表情 / 梗图 / 文字 |

## 使用流程
1. sticker_scan() → 扫描聊天中的贴纸（可能耗时）
2. sticker_list(unlabeled=True) → 查看未标注的贴纸
3. sticker_label(md5, label=..., emotion=..., content_type=...) → 标注贴纸
""",
}

TOPIC_ALIASES: dict[str, str] = {
    "入门": "getting-started",
    "分析": "workflow/analysis",
    "分析流程": "workflow/analysis",
    "报告": "report-template",
    "模板": "report-template",
    "报告模板": "report-template",
    "方法论": "methodology",
    "方法": "methodology",
    "事实": "rules/evidence",
    "证据": "rules/evidence",
    "权限": "rules/permissions",
    "权限管理": "rules/permissions",
    "回复": "rules/reply",
    "话术": "rules/reply",
    "维持": "workflow/maintain",
    "维护": "workflow/maintain",
    "客户维护": "workflow/maintain",
    "同步": "reference/sync",
    "公式": "reference/formula",
    "贴纸": "reference/stickers",
    "表情": "reference/stickers",
    "help": "getting-started",
    "analysis": "workflow/analysis",
    "report": "report-template",
    "template": "report-template",
    "methodology": "methodology",
    "evidence": "rules/evidence",
    "permission": "rules/permissions",
    "reply": "rules/reply",
    "maintain": "workflow/maintain",
    "sync": "reference/sync",
    "formula": "reference/formula",
    "sticker": "reference/stickers",
}


def _list_topics() -> str:
    """当 topic 不匹配时，返回可用主题列表。"""
    lines = ["# SalesCRM 使用指南", "", "可用主题：", ""]
    for key, name in [
        ("getting-started", "快速入门 — 三件事你必须知道 + 三个最常用场景"),
        ("workflow/analysis", "客户分析完整流程 — 从同步到保存的 6 步"),
        ("report-template", "分析报告模板 — 8 段式报告骨架"),
        ("methodology", "核心方法论 — Wiki 主轴 + 公式辅助 + 冲突裁决"),
        ("rules/evidence", "事实档案写入规则 — 自检三问 + 概念分层"),
        ("rules/permissions", "操作权限规范 — 哪些要确认、哪些直接执行"),
        ("rules/reply", "回复构造规则 — 话术 + 时间线 + 对话领导"),
        ("workflow/maintain", "客户维护工作流 — 候选人筛选 + 消息输出"),
        ("reference/sync", "同步策略速查 — 三种场景 + 范围限制"),
        ("reference/formula", "公式使用指南 — 两套公式系统 + 阈值 + 核验示例"),
        ("reference/stickers", "贴纸系统 — 镜像检测 + 标注体系"),
    ]:
        lines.append(f"- `{key}` — {name}")
    lines.append("")
    lines.append("用法：guide(topic='workflow/analysis')")
    return "\n".join(lines)


def guide_func(topic: str = "getting-started") -> str:
    """获取 SalesCRM MCP 使用指南。

    Args:
        topic: 主题名称。支持中文别名（如"分析"、"报告"、"方法论"）。
               默认返回快速入门指南。

    Returns:
        Markdown 格式的使用指南文本。
    """
    key = TOPIC_ALIASES.get(topic.lower().strip(), topic.lower().strip())
    content = GUIDES.get(key)
    if content is not None:
        return content
    return _list_topics()
