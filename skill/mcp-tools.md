# MCP 工具速查表

所有工具通过 MCP 协议调用。共 55 个工具。

---

## 数据获取（只读）

| 工具 | 参数 | 返回 | 用途 |
|------|------|------|------|
| `person_brief(name)` | 名字 | dict | 全局视图：身份+指标+事件+信号+Wiki推荐 |
| `person_chat(name, recent=30, keyword?, from_date?, context_lines=0)` | 名字+过滤 | dict | 聊天记录（结构化消息列表） |
| `person_metrics(name)` | 名字 | dict | 全部指标（composite/信号等级/16指标/动态信号） |
| `person_status(name)` | 名字 | dict | 精简状态快照（信号等级+消息统计+趋势） |
| `person_rank()` | 无 | dict | 全部客户商务热度排名 |
| `person_evidence(name, section="all")` | 名字+section | dict | 事实档案（timeline/evaluations/notes/dates/all） |
| `person_timeline(name)` | 名字 | dict | 关系时间线 |
| `person_signals(name)` | 名字 | dict | 信号详情（基础+操控+朋友圈联动） |
| `person_moments_stats(name)` | 名字 | dict | 朋友圈互动统计 |
| `person_compare(name)` | 名字 | dict | 对比 latest 和 previous 分析 |
| `maintain_list(limit=10)` | 数量 | dict | 需要维持关系的候选人列表 |
| `message_context(message_ids, before=20, after=20)` | 消息ID列表 | dict | 根据消息ID获取前后上下文 |

## Wiki / 知识库

| 工具 | 参数 | 返回 | 用途 |
|------|------|------|------|
| `wiki_search(query, limit=5)` | 关键词 | dict | 跨 Wiki/分析/KB 搜索 |
| `wiki_read(path, max_chars=8000)` | 文件路径 | dict | 读取 Wiki 页面全文 |
| `guide(topic)` | 主题名 | dict | 获取使用指南（11个主题） |

## 数据写入

| 工具 | 参数 | 用途 |
|------|------|------|
| `person_note(name, text)` | 名字+内容 | 添加备注到事实档案 |
| `person_date_record(name, date_text?, location?, rating?)` | 名字+会面信息 | 记录会面 |
| `person_evaluate(name, text)` | 名字+评估 | 记录主观评估 |
| `events_save(name, disconnect_days=7)` | 名字 | 检测+写入关系事件（一步完成） |
| `events_scan(name, disconnect_days=7)` | 名字 | 只检测不写入 |
| `save_from_markdown(name, markdown_text)` | 名字+Markdown | 【必须】保存完整分析报告（.md+.yaml） |
| `person_save_analysis(name, stage, confidence, ...)` | 分析结果 | 【可选】补充结构化数据到 YAML |
| `contact_alias(name, alias_type, value)` | 名字+别名 | 添加别名 |
| `contact_alias_remove(name, alias_type, value?)` | 名字+类型 | 删除别名 |
| `contact_merge(name1, name2)` | 两个名字 | 合并联系人（不可逆，需确认） |
| `sticker_label(md5, label, emotion?, content_type?)` | md5+标注 | 标注贴纸 |
| `exclude_add(name)` | 名字 | 加入排除列表 |
| `exclude_remove(name)` | 名字 | 移出排除列表 |
| `failure_add(name, text)` | 名字+内容 | 记录失败案例 |

## 同步

| 工具 | 参数 | 用途 |
|------|------|------|
| `person_sync(name)` | 名字 | 同步某客户的最新消息（几秒） |
| `system_sync(mode="incremental", meta_only=False)` | 模式+布尔 | 全局同步。meta_only=True 只同步联系人列表（1秒） |
| `sync_moments(name)` | 名字 | 同步朋友圈互动到事实档案 |
| `weekly_report(deep=False)` | 布尔 | 生成周报 |
| `wcd_status()` | 无 | 检查 WCD 后端状态+密钥缓存 |
| `wcd_start(timeout=90)` | 超时秒数 | 启动 WCD 后端（默认 90s） |

## 联系人管理

| 工具 | 参数 | 用途 |
|------|------|------|
| `contact_search(query)` | 查询词 | 搜索联系人 |
| `contact_alias(name, alias_type, value)` | 名字+别名 | 添加别名 |
| `contact_alias_remove(name, alias_type, value?)` | 名字+类型 | 删除别名 |
| `contact_merge(name1, name2)` | 两个名字 | 合并（不可逆） |
| `exclude_list()` | 无 | 查看排除列表 |
| `failure_list()` | 无 | 查看失败案例 |

## 战态公式（辅助参考）

| 工具 | 用途 |
|------|------|
| `formula_get_params(name)` | 获取战态公式自动参数 |
| `formula_calc_ivi(sp, fback, user_investment, pface)` | 意图真实度 |
| `formula_calc_spe(user_ddepth, target_ddepth, target_latency, user_latency)` | 社交势能 |
| `formula_calc_ews(gap_effect, cp_index, eev, scarcity_loss)` | 推进窗口期 |
| `formula_calc_is(...)` | 真实需求度 |
| `formula_calc_gap_effect(...)` | 情绪落差刺激 |
| `formula_calc_eev(...)` | 推进期望值 |
| `formula_calc_cs(...)` | 矛盾状态 |
| `formula_calc_action(ivi, spe, ews)` | 战态终极决策参考 |

## 销售公式（辅助参考，SalesCRM 独有）

| 工具 | 用途 |
|------|------|
| `sales_get_params(name)` | 获取销售公式自动参数 |
| `sales_calc_bq(sp, fback, user_investment, pface)` | 购买意愿真实度 |
| `sales_calc_bsp(user_ddepth, target_ddepth, target_latency, user_latency)` | 商务势能 |
| `sales_calc_bws(gap_effect, cp_index, eev, scarcity_loss)` | 购买窗口期 |
| `sales_calc_pv(p_succ, escalation_bonus, p_fail, loss_risk)` | 成交期望值 |
| `sales_calc_action(bq, bsp, bws)` | 销售行动决策（bargain/push/nurture/reset/maintain） |

⚠️ 公式数值只在"数据全貌"表出现一次，不主导策略。详见 `mcp-methodology.md`。

## 贴纸

| 工具 | 参数 | 用途 |
|------|------|------|
| `sticker_scan(name)` | 名字 | 扫描聊天中的贴纸（可能耗时） |
| `sticker_list(name, unlabeled=False)` | 名字 | 查看贴纸列表 |
| `sticker_label(md5, label, emotion?, content_type?)` | md5+标注 | 标注贴纸 |

## guide 工具主题

| 主题 | 内容 |
|------|------|
| `getting-started` | 快速入门 |
| `workflow/analysis` | 客户分析完整流程 |
| `report-template` | 分析报告模板 |
| `methodology` | 核心方法论 |
| `rules/evidence` | 事实档案写入规则 |
| `rules/permissions` | 操作权限规范 |
| `rules/reply` | 回复构造规则 |
| `workflow/maintain` | 客户维护工作流 |
| `reference/sync` | 同步策略速查 |
| `reference/formula` | 公式使用指南 |
| `reference/stickers` | 贴纸系统说明 |
