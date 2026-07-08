"""MCP 服务器入口。

使用 FastMCP 在 stdio 上提供工具服务。
SalesCRM 版本：55 个工具（23 只读含 guide + 17 写入 + 15 公式）。
"""

import sys

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
        sys.stdin.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        # stdin 可能在测试环境下被替换（DontReadFromInput），忽略
        pass

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from fastmcp import FastMCP

from mcp_server import tools_read, tools_write, tools_formula, tools_guide, tools_config, tools_workflow

mcp = FastMCP("SalesCRM")

# ── 注册 guide 工具（使用指南和工作流文档）──────────────────────

mcp.tool(
    name="guide",
    description="获取 SalesCRM MCP 使用指南和工作流文档。Agent 在不确定操作流程时调用。"
               "主题：getting-started（快速入门）/ workflow/analysis（分析流程）/ "
               "report-template（报告模板）/ methodology（方法论）/ "
               "rules/evidence（事实写入规则）/ rules/permissions（权限规范）/ "
               "rules/reply（回复构造规则）/ workflow/maintain（客户维护）/ "
               "reference/sync（同步策略）/ reference/formula（公式指南）/ "
               "reference/stickers（贴纸系统）",
    annotations={"readOnlyHint": True},
)(tools_guide.guide_func)

# ── 注册配置工具（后端切换，不重启即可生效）───────────────────────

mcp.tool(
    name="get_backend",
    description="查看当前数据后端配置（wcd/weflow）",
    annotations={"readOnlyHint": True},
)(tools_config.get_backend)

mcp.tool(
    name="set_backend",
    description="切换数据后端（wcd 或 weflow），可选同时更新 base_url 和 token。写入 config.yaml 后即时生效，不需要重启 MCP Server",
)(tools_config.set_backend)

# ── Phase 1: 核心只读工具（6 个）──────────────────────────────

mcp.tool(
    name="person_brief",
    description="获取客户简要信息（身份/消息统计/指标/事件/信号/最近消息/Wiki推荐/relationship_stage/recommended_wiki_queries）。"
               "⚠️调此工具前必须先调 person_sync 同步最新消息。"
               "看到信号后，将 recommended_wiki_queries + relationship_stage 传给 wiki_context 建立方法论框架。"
               "详见 guide('workflow/analysis')",
    annotations={"readOnlyHint": True},
)(tools_read.person_brief)

mcp.tool(
    name="person_chat",
    description="获取客户聊天记录（按日期分组，已标注'我'/'对方'名字）。"
               "【下一步建议】看到聊天模式后调 wiki_search 找话术策略和互动技巧",
    annotations={"readOnlyHint": True},
)(tools_read.person_chat)

mcp.tool(
    name="person_metrics",
    description="获取客户关系指标（回复率、回复速度、情绪评分等）。"
               "【下一步建议】看到数值后调 wiki_search 解读指标背后的含义，或用 sales_calc_bq 核验",
    annotations={"readOnlyHint": True},
)(tools_read.person_metrics)

mcp.tool(
    name="person_rank",
    description="获取所有客户的商务热度排名",
    annotations={"readOnlyHint": True},
)(tools_read.person_rank)

mcp.tool(
    name="person_status",
    description="获取客户状态概览（精简版指标，快速了解当前状态）",
    annotations={"readOnlyHint": True},
)(tools_read.person_status)

mcp.tool(
    name="wiki_search",
    description="搜索 Wiki 知识库（销售知识、技巧、场景应对策略）。"
               "【下一步建议】找到条目后用 wiki_read 读全文，然后结合数据验证框架",
    annotations={"readOnlyHint": True},
)(tools_read.wiki_search)

# ── Phase 2 P0: wiki_read ────────────────────────────────────

mcp.tool(
    name="wiki_read",
    description="读取 Wiki 页面完整正文（wiki_search 找到路径后用此工具读全文）",
    annotations={"readOnlyHint": True},
)(tools_read.wiki_read)

# ── wiki_context（推荐主入口）───────────────────────────────────

mcp.tool(
    name="wiki_context",
    description="【推荐·Wiki 主入口】批量构建 Wiki 知识上下文。传入多条查询 + 当前关系阶段 + 分析焦点，"
               "一次返回格式化 prompt 段落（合并去重+阶段加权+预算裁剪）。"
               "替代分析流程中多次 wiki_search+wiki_read 的重复调用。"
               "参数：queries（查询列表，最多5条，超出自动截断）/ task_type（reply/meet/ask/analyze，默认analyze）/ "
               "stage（销售阶段，从 person_brief 的 relationship_stage 获取）/ "
               "focus（signals/strategy/risk/date/chat）/ max_chars（默认8000）/ max_pages（默认8）。"
               "返回：prompt_section（可直接嵌入推理的 Markdown 段落）+ meta + page_list。"
               "注意：wiki_search+wiki_read 保留用于精确单页钻取，wiki_context 是批量建框架的主入口。",
    annotations={"readOnlyHint": True},
)(tools_read.wiki_context)

# ── Phase 1: 写入工具（2 个）──────────────────────────────────

mcp.tool(
    name="person_note",
    description="添加客户备注到事实档案",
)(tools_write.person_note)

mcp.tool(
    name="person_date_record",
    description="记录会面信息",
)(tools_write.person_date_record)

# ── Phase 2 P0: sync_person + save_analysis ──────────────────

mcp.tool(
    name="person_sync",
    description="⚠️【分析前置·必须调用】增量同步单个客户最新消息。分析任何客户之前必须先调此工具，否则看到的是旧数据。"
               "一般几秒完成。如果联系人搜不到，改用 system_sync(meta_only=True)。"
               "【下一步建议】调 person_brief 获取全局视图，或 workflow_step('analysis') 查看完整分析流程",
)(tools_write.person_sync)

mcp.tool(
    name="person_save_analysis",
    description="⚠️【覆盖写入·可选】保存结构化分析到 YAML（用于 person_compare 对比）。"
               "覆盖 latest.yaml，旧版本自动转为 previous.yaml，同时 history/ 目录保留带时间戳的历史副本。"
               "返回 previous_info（被覆盖的旧版本路径/大小/生成时间）和 changed_fields（本次变更字段），调用方可据此告知用户。"
               "如需保存完整 Markdown 报告请用 save_from_markdown。"
               "参数：stage（阶段）/ confidence（置信度 0-1）/ reasoning（推理过程）/ diagnosis（诊断）/ "
               "strategy（策略）/ risks（风险列表）/ signals（信号列表）/ "
               "evidence_refs（证据引用: message_id+quote+note）/ metric_snapshot（指标快照）/ data_window（数据窗口）",
)(tools_write.person_save_analysis)

# ── Phase 2 P1: 只读工具（10 个）──────────────────────────────

mcp.tool(
    name="person_timeline",
    description="获取客户关系时间线（关键事件按时间排列）",
    annotations={"readOnlyHint": True},
)(tools_read.person_timeline)

mcp.tool(
    name="person_signals",
    description="获取信号详情（基础信号 + 操控信号 + 朋友圈联动信号）",
    annotations={"readOnlyHint": True},
)(tools_read.person_signals)

mcp.tool(
    name="person_evidence",
    description="获取事实档案（已记录的笔记、评价、会面等客观事实）",
    annotations={"readOnlyHint": True},
)(tools_read.person_evidence)

mcp.tool(
    name="person_compare",
    description="对比 latest 和 previous 分析的变化趋势",
    annotations={"readOnlyHint": True},
)(tools_read.person_compare)

mcp.tool(
    name="weekly_report",
    description="生成周报（本周客户维护总结）",
    annotations={"readOnlyHint": True},
)(tools_read.weekly_report)

mcp.tool(
    name="person_moments_stats",
    description="获取朋友圈互动统计",
    annotations={"readOnlyHint": True},
)(tools_read.person_moments_stats)

mcp.tool(
    name="maintain_list",
    description="获取需要维持关系的候选人列表。拿结果后对每人调 person_brief/person_chat/person_metrics 获取详情，输出具体可发送的消息。详细流程见 guide('workflow/maintain')",
    annotations={"readOnlyHint": True},
)(tools_read.maintain_list)

mcp.tool(
    name="events_scan",
    description="扫描关系事件（只读，不写入）",
    annotations={"readOnlyHint": True},
)(tools_read.events_scan)

mcp.tool(
    name="wcd_status",
    description="检查 WCD 后端在线状态和密钥缓存状态（只读检测，不启动进程）。如果显示 offline，请调 wcd_start 启动后端",
    annotations={"readOnlyHint": True},
)(tools_read.wcd_status)

mcp.tool(
    name="wcd_start",
    description="启动 WCD 后端进程并等待健康检查通过。如果 WCD 已在运行则直接返回成功。"
               "默认等待 90s（WCD 冷启动通常需要 40-60s）。超时返回 process_alive 字段区分"
               "'进程仍在运行但健康检查未就绪'和'进程已退出'两种情况。"
               "使用场景：wcd_status 显示 offline 时调此工具启动后端",
)(tools_read.wcd_start)

mcp.tool(
    name="weflow_status",
    description="检查 WeFlow 后端在线状态（只读检测，不启动进程）。如果显示 offline，请调 weflow_start 启动后端",
    annotations={"readOnlyHint": True},
)(tools_read.weflow_status)

mcp.tool(
    name="weflow_start",
    description="启动 WeFlow 后端进程（D:\\WeFlow\\WeFlow.exe）并等待健康检查通过。如果 WeFlow 已在运行则直接返回成功。默认等待 60s",
)(tools_read.weflow_start)

# ── Phase 2 P1: events 拆分 + 同步 + 评价（3 个写入）──────────

mcp.tool(
    name="events_save",
    description="检测并写入关系事件到事实档案（一步完成检测+写入）。"
               "建议先调 events_scan 展示结果供用户确认，但非强制——直接调用本工具会自动检测并写入。"
               "disconnect_days 控制断联判定阈值（默认 7 天）",
)(tools_write.events_save)

mcp.tool(
    name="person_evaluate",
    description="添加主观评价到事实档案（⚠️概念上属于分析归档，优先级低于客观事实）。Agent 读取时应保持批判性，不能与 note/date/events 的客观事实同等对待",
)(tools_write.person_evaluate)

mcp.tool(
    name="system_sync",
    description="全量/增量数据同步（⚠️ 可能耗时 1-5 分钟，需 WCD 后端运行）",
)(tools_read.system_sync)

# ── Phase 2 P2: 只读工具拆分（6 个）──────────────────────────

mcp.tool(
    name="contact_search",
    description="搜索联系人信息（身份目录查询）",
    annotations={"readOnlyHint": True},
)(tools_read.contact_search)

mcp.tool(
    name="sticker_scan",
    description="扫描聊天中的贴纸表情（⚠️ 可能耗时）",
    annotations={"readOnlyHint": True},
)(tools_read.sticker_scan)

mcp.tool(
    name="sticker_list",
    description="列出贴纸词典",
    annotations={"readOnlyHint": True},
)(tools_read.sticker_list)

mcp.tool(
    name="exclude_list",
    description="查看排除列表（硬排除 + 标签排除 + 手动排除）",
    annotations={"readOnlyHint": True},
)(tools_read.exclude_list)

mcp.tool(
    name="failure_list",
    description="查看所有失败案例",
    annotations={"readOnlyHint": True},
)(tools_read.failure_list)

mcp.tool(
    name="message_context",
    description="根据消息 ID 获取前后上下文消息（不跨会话）",
    annotations={"readOnlyHint": True},
)(tools_read.message_context)

# ── Phase 2 P2: 写入工具拆分（8 个）──────────────────────────

mcp.tool(
    name="contact_alias",
    description="为联系人添加别名（写错可调 contact_alias_remove 删除后重设）",
)(tools_write.contact_alias)

mcp.tool(
    name="contact_alias_remove",
    description="删除联系人的别名（alias_type 必填，value 空则删该类型全部）",
)(tools_write.contact_alias_remove)

mcp.tool(
    name="contact_merge",
    description="⚠️【必须确认】合并两个联系人（不可逆！source 的所有 account 和 alias 转移到 target，source 记录被删除）。执行前必须征得用户明确同意",
)(tools_write.contact_merge)

mcp.tool(
    name="sticker_label",
    description="标注贴纸含义（情绪、内容类型）",
)(tools_write.sticker_label)

mcp.tool(
    name="exclude_add",
    description="将联系人加入手动排除列表",
)(tools_write.exclude_add)

mcp.tool(
    name="exclude_remove",
    description="将联系人从手动排除列表移除",
)(tools_write.exclude_remove)

mcp.tool(
    name="failure_add",
    description="记录失败案例（客户关系结束后记录教训）",
)(tools_write.failure_add)

mcp.tool(
    name="save_from_markdown",
    description="⚠️【分析完成·必须调用】保存完整 Markdown 分析报告。"
               "同时生成两个文件：latest.md（完整 Markdown 报告）+ latest.yaml（结构化数据）。"
               "报告必须详细（8 段式），不能只列公式数值和一句话结论。"
               "建议先用 guide('report-template') 获取报告模板。",
)(tools_write.save_from_markdown_tool)

mcp.tool(
    name="sync_moments",
    description="同步朋友圈互动到事实档案",
)(tools_write.sync_moments_tool)

# ── Phase 3 P3: 战态分析公式（9 个纯计算函数）─────────────────

mcp.tool(
    name="formula_get_params",
    description="【辅助参考】获取战态公式参数（从数据库自动计算分析所需参数）。先调此工具获取自动参数，manual 参数需自行判断",
    annotations={"readOnlyHint": True},
)(tools_formula.formula_get_params)

mcp.tool(
    name="formula_calc_ivi",
    description="【辅助参考·核验而非套用】计算 IVI（意图真实度）。阈值（>1.0真实意向，<0.5敷衍）仅是参考视角，不是裁判。"
               "先调 formula_get_params 获取自动参数，manual 参数（Pface 等）需自行判断。"
               "结果只在数据全貌表出现一次，不主导策略。最终判断依据 Wiki 知识 + 事实档案",
    annotations={"readOnlyHint": True},
)(tools_formula.formula_calc_ivi)

mcp.tool(
    name="formula_calc_spe",
    description="【辅助参考·核验而非套用】计算 SPE（社交势能）。阈值（0.8-1.5健康，<0.6红线）仅是参考视角，不是裁判。"
               "先调 formula_get_params 获取自动参数，manual 参数需自行判断。"
               "结果只在数据全貌表出现一次，不主导策略。最终判断依据 Wiki 知识 + 事实档案",
    annotations={"readOnlyHint": True},
)(tools_formula.formula_calc_spe)

mcp.tool(
    name="formula_calc_ews",
    description="【辅助参考·核验而非套用】计算 EWS（推进窗口期）。阈值（>0.8出击，<0.3关闭）仅是参考视角，不是裁判。"
               "先调 formula_get_params 获取自动参数，manual 参数需自行判断。"
               "结果只在数据全貌表出现一次，不主导策略。最终判断依据 Wiki 知识 + 事实档案",
    annotations={"readOnlyHint": True},
)(tools_formula.formula_calc_ews)

mcp.tool(
    name="formula_calc_is",
    description="【辅助参考·核验而非套用】计算 IS（真实合作度）。阈值（>0.5高合作度）仅是参考视角，不是裁判。"
               "先调 formula_get_params 获取自动参数，manual 参数需自行判断。"
               "结果只在数据全貌表出现一次，不主导策略。最终判断依据 Wiki 知识 + 事实档案",
    annotations={"readOnlyHint": True},
)(tools_formula.formula_calc_is)

mcp.tool(
    name="formula_calc_gap_effect",
    description="【辅助参考·核验而非套用】计算 Gap_Effect（情绪落差刺激）。结果仅是参考视角，不是裁判。"
               "先调 formula_get_params 获取自动参数。"
               "结果只在数据全貌表出现一次，不主导策略。最终判断依据 Wiki 知识 + 事实档案",
    annotations={"readOnlyHint": True},
)(tools_formula.formula_calc_gap_effect)

mcp.tool(
    name="formula_calc_eev",
    description="【辅助参考·核验而非套用】计算 EEV（推进期望值）。阈值（>0.3值得出击）仅是参考视角，不是裁判。"
               "先调 formula_get_params 获取自动参数，manual 参数需自行判断。"
               "结果只在数据全貌表出现一次，不主导策略。最终判断依据 Wiki 知识 + 事实档案",
    annotations={"readOnlyHint": True},
)(tools_formula.formula_calc_eev)

mcp.tool(
    name="formula_calc_cs",
    description="【辅助参考·核验而非套用】计算 CS（矛盾演化状态）。阈值（>0欲望占主导）仅是参考视角，不是裁判。"
               "先调 formula_get_params 获取自动参数，manual 参数需自行判断。"
               "结果只在数据全貌表出现一次，不主导策略。最终判断依据 Wiki 知识 + 事实档案",
    annotations={"readOnlyHint": True},
)(tools_formula.formula_calc_cs)

mcp.tool(
    name="formula_calc_action",
    description="【辅助参考·核验而非套用】终极行动决策 — 基于 IVI/SPE/EWS 的策略分发（推进/拉扯/重置/维持）。"
               "参考视角，不是裁判。结果只在数据全貌表出现一次，不主导策略。最终判断依据 Wiki 知识 + 事实档案",
    annotations={"readOnlyHint": True},
)(tools_formula.formula_calc_action)

# ── Phase 3 P3: 销售决策公式（6 个，SalesCRM 独有）────────────

mcp.tool(
    name="sales_get_params",
    description="【辅助参考】获取销售公式参数（从数据库自动计算 BQ/BSP/BWS/PV 所需参数）。先调此工具获取自动参数，manual 参数需自行判断",
    annotations={"readOnlyHint": True},
)(tools_formula.sales_get_params)

mcp.tool(
    name="sales_calc_bq",
    description="【辅助参考·核验而非套用】计算 BQ（购买意愿真实度）。阈值（>1.0强烈信号，<0.5敷衍）仅是参考视角，不是裁判。"
               "先调 sales_get_params 获取自动参数，manual 参数（Pface 等）需自行判断。"
               "结果只在数据全貌表出现一次，不主导策略。最终判断依据 Wiki 知识 + 事实档案",
    annotations={"readOnlyHint": True},
)(tools_formula.sales_calc_bq)

mcp.tool(
    name="sales_calc_bsp",
    description="【辅助参考·核验而非套用】计算 BSP（商务势能）。阈值（0.8-1.5健康，<0.6高危低位）仅是参考视角，不是裁判。"
               "先调 sales_get_params 获取自动参数，manual 参数需自行判断。"
               "结果只在数据全貌表出现一次，不主导策略。最终判断依据 Wiki 知识 + 事实档案",
    annotations={"readOnlyHint": True},
)(tools_formula.sales_calc_bsp)

mcp.tool(
    name="sales_calc_bws",
    description="【辅助参考·核验而非套用】计算 BWS（购买意向期）。阈值（>0.8出击，<0.3关闭）仅是参考视角，不是裁判。"
               "先调 sales_get_params 获取自动参数，manual 参数需自行判断。"
               "结果只在数据全貌表出现一次，不主导策略。最终判断依据 Wiki 知识 + 事实档案",
    annotations={"readOnlyHint": True},
)(tools_formula.sales_calc_bws)

mcp.tool(
    name="sales_calc_pv",
    description="【辅助参考·核验而非套用】计算 PV（成交期望值）。阈值（>0.3值得推进）仅是参考视角，不是裁判。"
               "先调 sales_get_params 获取自动参数，manual 参数需自行判断。"
               "结果只在数据全貌表出现一次，不主导策略。最终判断依据 Wiki 知识 + 事实档案",
    annotations={"readOnlyHint": True},
)(tools_formula.sales_calc_pv)

mcp.tool(
    name="sales_calc_action",
    description="【辅助参考·核验而非套用】销售行动决策 — 基于 BQ/BSP/BWS 的策略分发（bargain/push/nurture/reset/maintain）。"
               "参考视角，不是裁判。结果只在数据全貌表出现一次，不主导策略。最终判断依据 Wiki 知识 + 事实档案",
    annotations={"readOnlyHint": True},
)(tools_formula.sales_calc_action)

# ── Skill-MCP 融合工具（双向导航）─────────────────────────────

mcp.tool(
    name="skill_map",
    description="【Skill-MCP 融合】查询工具与 Skill 的双向映射关系。"
               "输入工具名返回下一步建议和 Skill 参考，不输入则返回所有工具概览。"
               "用法：skill_map('person_brief') 查特定工具，skill_map() 查看全部",
    annotations={"readOnlyHint": True},
)(tools_workflow.skill_map)

mcp.tool(
    name="workflow_step",
    description="【Skill-MCP 融合】按步骤执行工作流，返回下一步指引。"
               "支持工作流：analysis（客户分析）/ emergency_reply（紧急回复）/ weekly（周报）/ maintain（维持关系）。"
               "用法：workflow_step('analysis') 查看流程概览，workflow_step('analysis', 0) 获取第0步详情",
    annotations={"readOnlyHint": True},
)(tools_workflow.workflow_step)

if __name__ == "__main__":
    mcp.run()
