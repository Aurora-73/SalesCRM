# SalesCRM MCP 工具映射表

> engine/tools.py 函数 → MCP 工具名 映射关系

## 只读工具（23 个）

| MCP 工具名 | engine/tools.py 函数 | 返回类型 | 说明 |
|-----------|---------------------|---------|------|
| `person_brief` | `brief_data(name)` | dict | 客户简要信息 |
| `person_chat` | `chat_data(name, ...)` | dict | 聊天记录 |
| `person_metrics` | `metrics(name)` | dict | 关系指标 |
| `person_rank` | `rank_data()` | dict | 商务热度排名 |
| `person_status` | `status_data(name)` | dict | 状态概览 |
| `wiki_search` | `wiki_search_data(query, limit)` | dict | Wiki 搜索 |
| `wiki_read` | `wiki_show(path, max_chars)` | dict | Wiki 页面正文 |
| `person_timeline` | `timeline(name, max_events)` | dict | 关系时间线 |
| `person_signals` | `signals(name)` | dict | 信号详情 |
| `person_evidence` | `evidence(name, section, since_date)` | dict | 事实档案 |
| `person_compare` | `compare_analysis(name)` | dict | 历史分析对比 |
| `weekly_report` | `weekly(deep)` | dict | 周报 |
| `person_moments_stats` | `moments_stats(name)` | dict | 朋友圈统计 |
| `maintain_list` | `maintain_candidates(max_people)` | dict | 维持关系候选人 |
| `events_scan` | `events(name, scan=False, ...)` | dict | 事件扫描（只读） |
| `wcd_status` | (内联实现) | dict | WCD 状态检查 |
| `contact_search` | `contact(query, action="search")` | dict | 联系人搜索 |
| `sticker_scan` | `sticker(action="scan", ...)` | dict | 贴纸扫描 |
| `sticker_list` | `sticker(action="list", ...)` | dict | 贴纸列表 |
| `exclude_list` | `exclude(action="list")` | dict | 排除列表 |
| `failure_list` | `failure(action="list")` | dict | 失败案例 |
| `message_context` | `message_context_data(message_ids, ...)` | dict | 消息上下文 |

## 写入工具（15 个）

| MCP 工具名 | engine/tools.py 函数 | 风险等级 | 说明 |
|-----------|---------------------|---------|------|
| `person_note` | `note(name, content)` | 追加 | 客户备注 |
| `person_date_record` | `date(name, date_text, ...)` | 追加 | 会面记录 |
| `person_sync` | `sync_person(name, mode)` | 同步 | 增量同步 |
| `person_save_analysis` | `save_analysis(name, **kwargs)` | 覆盖 | 保存分析 |
| `events_save` | `events(name, scan=True, ...)` | 追加 | 写入事件 |
| `person_evaluate` | `evaluate(name, text)` | 追加 | 客户评价 |
| `system_sync` | `sync(mode, meta_only)` | 同步 | 全量同步 |
| `contact_alias` | `contact(query, action="alias", ...)` | 追加 | 添加别名 |
| `contact_merge` | `contact(source, action="merge", ...)` | ⚠️ 不可逆 | 合并联系人 |
| `sticker_label` | `sticker(action="label", ...)` | 追加 | 标注贴纸 |
| `exclude_add` | `exclude(action="add", ...)` | 修改 | 加入排除 |
| `exclude_remove` | `exclude(action="remove", ...)` | 修改 | 移出排除 |
| `failure_add` | `failure(action="add", ...)` | 追加 | 记录失败 |
| `save_from_markdown` | `save_from_markdown(name, md)` | 覆盖 | Markdown 保存 |
| `sync_moments` | `sync_moments(name)` | 追加 | 同步朋友圈 |

## 公式工具（15 个）

### 战态分析公式（9 个）

| MCP 工具名 | engine/formulas.py 函数 | 参数校验 | 说明 |
|-----------|------------------------|---------|------|
| `formula_get_params` | `formula_params(name)` | — | 获取参数 |
| `formula_calc_ivi` | `formula_ivi(sp, fback, ...)` | clamp [0,1] | 意图真实度 |
| `formula_calc_spe` | `formula_spe(user_ddepth, ...)` | clamp [0,1] | 社交势能 |
| `formula_calc_ews` | `formula_ews(gap_effect, ...)` | clamp [0,1] | 推进窗口期 |
| `formula_calc_is` | `formula_is(backstage, pface)` | clamp [0,1] | 真实合作度 |
| `formula_calc_gap_effect` | `formula_gap_effect(act, exp)` | clamp [0,1] | 情绪落差 |
| `formula_calc_eev` | `formula_eev(p_succ, ...)` | clamp [0,1] | 推进期望值 |
| `formula_calc_cs` | `formula_cs(internal_d, external_r)` | clamp [0,1] | 矛盾状态 |
| `formula_calc_action` | `formula_action(ivi, spe, ...)` | 不 clamp | 行动决策 |

### 销售决策公式（6 个）

| MCP 工具名 | engine/formulas_sales.py 函数 | 参数校验 | 说明 |
|-----------|-------------------------------|---------|------|
| `sales_get_params` | `sales_params(name)` | — | 获取参数 |
| `sales_calc_bq` | `sales_bq(sp, fback, ...)` | clamp [0,1] | 购买意愿真实度 |
| `sales_calc_bsp` | `sales_bsp(user_ddepth, ...)` | clamp [0,1] | 商务势能 |
| `sales_calc_bws` | `sales_bws(gap_effect, ...)` | clamp [0,1] | 购买意向期 |
| `sales_calc_pv` | `sales_pv(p_succ, ...)` | clamp [0,1] | 成交期望值 |
| `sales_calc_action` | `sales_action(bq, bsp, ...)` | 不 clamp | 销售行动决策 |

## 永不暴露

| 函数 | 原因 |
|------|------|
| `fetch_keys` | 会重启微信并要求扫码，AI 无法完成，且有封号风险 |
