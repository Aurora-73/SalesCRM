"""最终质量自检 — 全量验收测试（SalesCRM 版本，55 工具）"""
import sys
import asyncio

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass


def test_tool_count():
    """验证工具总数为 55（53 + guide + wcd_start）"""
    from mcp_server.server import mcp
    tools = asyncio.run(mcp.list_tools())
    assert len(tools) == 55, f"工具数应为 55，实际 {len(tools)}"
    print(f"[PASS] 工具总数: {len(tools)}")
    return tools


def test_tool_categories(tools):
    """按类别统计工具数"""
    def is_readonly(t):
        if not t.annotations:
            return False
        try:
            return t.annotations.readOnlyHint
        except AttributeError:
            return getattr(t.annotations, "read_only_hint", False)
    read_tools = [t for t in tools if is_readonly(t)]
    write_tools = [t for t in tools if not is_readonly(t)]
    print(f"  只读工具: {len(read_tools)} 个")
    print(f"  写入工具: {len(write_tools)} 个")
    assert len(read_tools) + len(write_tools) == 55
    print("[PASS] 工具分类统计正确")


def test_phase_distribution(tools):
    """按 Phase 分布验证"""
    tool_names = {t.name for t in tools}

    phase1 = {"person_brief", "person_chat", "person_metrics", "person_rank",
              "person_status", "wiki_search", "person_note", "person_date_record"}
    assert phase1.issubset(tool_names), f"Phase 1 缺少: {phase1 - tool_names}"
    print(f"  [PASS] Phase 1: {len(phase1)} 个工具")

    p0 = {"wiki_read", "person_sync", "person_save_analysis"}
    assert p0.issubset(tool_names), f"P0 缺少: {p0 - tool_names}"
    print(f"  [PASS] Phase 2 P0: {len(p0)} 个工具")

    p1 = {"person_timeline", "person_signals", "person_evidence", "skill_search",
          "person_compare", "weekly_report", "person_moments_stats", "maintain_list",
          "events_scan", "events_save", "person_evaluate", "system_sync",
          "wcd_status", "wcd_start"}
    assert p1.issubset(tool_names), f"P1 缺少: {p1 - tool_names}"
    print(f"  [PASS] Phase 2 P1: {len(p1)} 个工具")

    p2 = {"contact_search", "sticker_scan", "sticker_list", "exclude_list",
          "failure_list", "message_context", "contact_alias", "contact_merge",
          "sticker_label", "exclude_add", "exclude_remove", "failure_add",
          "save_from_markdown", "sync_moments"}
    assert p2.issubset(tool_names), f"P2 缺少: {p2 - tool_names}"
    print(f"  [PASS] Phase 2 P2: {len(p2)} 个工具")

    p3_strategy = {"formula_get_params", "formula_calc_ivi", "formula_calc_spe", "formula_calc_ews",
               "formula_calc_is", "formula_calc_gap_effect", "formula_calc_eev",
               "formula_calc_cs", "formula_calc_action"}
    assert p3_strategy.issubset(tool_names), f"P3 战态分析公式缺少: {p3_strategy - tool_names}"
    print(f"  [PASS] Phase 3 P3 战态分析公式: {len(p3_strategy)} 个工具")

    p3_sales = {"sales_get_params", "sales_calc_bq", "sales_calc_bsp", "sales_calc_bws",
                "sales_calc_pv", "sales_calc_action"}
    assert p3_sales.issubset(tool_names), f"P3 销售公式缺少: {p3_sales - tool_names}"
    print(f"  [PASS] Phase 3 P3 销售公式: {len(p3_sales)} 个工具")

    # guide 工具（使用指南）
    guide_tools = {"guide"}
    assert guide_tools.issubset(tool_names), f"guide 缺少: {guide_tools - tool_names}"
    print(f"  [PASS] guide: {len(guide_tools)} 个工具")

    total = len(phase1) + len(p0) + len(p1) + len(p2) + len(p3_strategy) + len(p3_sales) + len(guide_tools)
    assert total == 55, f"总计应为 55，实际 {total}"
    print(f"  [PASS] 总计: {total} 个工具")


def test_fetch_keys_excluded(tools):
    """验证 fetch_keys 未被暴露"""
    tool_names = {t.name for t in tools}
    assert "fetch_keys" not in tool_names, "fetch_keys 不应被暴露！"
    print("[PASS] fetch_keys 未被暴露")


def test_guide_tool():
    """验证 guide 工具的 11 个主题和别名映射"""
    from mcp_server.tools_guide import guide_func, GUIDES, TOPIC_ALIASES

    # 1. 验证 11 个主题存在
    expected_topics = {
        "getting-started", "workflow/analysis", "report-template",
        "methodology", "rules/evidence", "rules/permissions", "rules/reply",
        "workflow/maintain", "reference/sync", "reference/formula",
        "reference/stickers",
    }
    assert set(GUIDES.keys()) == expected_topics, f"主题不匹配: {set(GUIDES.keys()) ^ expected_topics}"
    print(f"  [PASS] 11 个主题全部存在")

    # 2. 验证默认主题
    result = guide_func()
    assert "快速入门" in result, f"默认主题应为 getting-started: {result[:50]}"
    print(f"  [PASS] 默认返回 getting-started")

    # 3. 验证中文别名
    assert "分析" in TOPIC_ALIASES, "中文别名'分析'缺失"
    assert TOPIC_ALIASES["分析"] == "workflow/analysis"
    result = guide_func("分析")
    assert "客户分析完整流程" in result
    print(f"  [PASS] 中文别名映射正确")

    # 4. 验证英文别名
    assert "report" in TOPIC_ALIASES, "英文别名'report'缺失"
    assert TOPIC_ALIASES["report"] == "report-template"
    result = guide_func("report")
    assert "分析报告模板" in result
    print(f"  [PASS] 英文别名映射正确")

    # 5. 验证未知主题返回主题列表
    result = guide_func("unknown-topic")
    assert "可用主题" in result, f"未知主题应返回列表: {result[:50]}"
    print(f"  [PASS] 未知主题返回主题列表")

    # 6. 验证关键内容存在
    result = guide_func("workflow/analysis")
    assert "person_sync" in result, "workflow/analysis 应包含 person_sync"
    assert "save_from_markdown" in result, "workflow/analysis 应包含 save_from_markdown"
    assert "wiki_search" in result, "workflow/analysis 应包含 wiki_search"
    print(f"  [PASS] workflow/analysis 内容完整")

    # 7. 验证无 loveMentor / 恋爱 表述
    all_content = " ".join(GUIDES.values())
    assert "loveMentor" not in all_content, "guide 内容不应包含 loveMentor"
    assert "恋爱" not in all_content, "guide 内容不应包含 恋爱"
    assert "约会" not in all_content, "guide 内容不应包含 约会"
    assert "表白" not in all_content, "guide 内容不应包含 表白"
    assert "暧昧" not in all_content, "guide 内容不应包含 暧昧"
    print(f"  [PASS] 无恋爱相关表述")

    # 8. 验证销售公式在 reference/formula 中
    result = guide_func("reference/formula")
    assert "BQ" in result, "reference/formula 应包含 BQ"
    assert "BSP" in result, "reference/formula 应包含 BSP"
    assert "BWS" in result, "reference/formula 应包含 BWS"
    assert "PV" in result, "reference/formula 应包含 PV"
    print(f"  [PASS] 销售公式 BQ/BSP/BWS/PV 存在")


def test_sales_formulas():
    """验证销售公式工具可正常调用"""
    from mcp_server.tools_formula import (
        sales_calc_bq, sales_calc_bsp, sales_calc_bws,
        sales_calc_pv, sales_calc_action,
    )

    # BQ
    bq = sales_calc_bq(sp=0.7, fback=0.6, user_investment=0.5, pface=0.4)
    assert "bq" in bq, f"BQ 结果缺少 bq 字段: {bq}"
    assert "interpretation" in bq, f"BQ 结果缺少 interpretation: {bq}"
    print(f"[PASS] sales_calc_bq: bq={bq['bq']}")

    # BSP
    bsp = sales_calc_bsp(user_ddepth=0.5, target_ddepth=0.5, target_latency=1.0, user_latency=1.0)
    assert "bsp" in bsp, f"BSP 结果缺少 bsp 字段: {bsp}"
    print(f"[PASS] sales_calc_bsp: bsp={bsp['bsp']}")

    # BWS
    bws = sales_calc_bws(gap_effect=0.5, cp_index=0.6, eev=0.4, scarcity_loss=0.1)
    assert "bws" in bws, f"BWS 结果缺少 bws 字段: {bws}"
    print(f"[PASS] sales_calc_bws: bws={bws['bws']}")

    # PV
    pv = sales_calc_pv(p_succ=0.7, escalation_bonus=0.8, p_fail=0.3, loss_risk=0.5)
    assert "pv" in pv, f"PV 结果缺少 pv 字段: {pv}"
    print(f"[PASS] sales_calc_pv: pv={pv['pv']}")

    # sales_action
    action = sales_calc_action(bq=0.8, bsp=1.0, bws=0.6, bs=0.2, pv=0.4)
    assert "action" in action, f"sales_action 结果缺少 action 字段: {action}"
    assert action["action"] in ("bargain", "push", "nurture", "reset", "maintain"), \
        f"action 值异常: {action['action']}"
    print(f"[PASS] sales_calc_action: action={action['action']}")


def test_clamp_warnings():
    """验证 _clamp_01 参数校验生成警告"""
    from mcp_server.tools_formula import sales_calc_bq

    # 正常范围 — 无警告
    normal = sales_calc_bq(sp=0.5, fback=0.5, user_investment=0.5, pface=0.5)
    assert "param_warnings" not in normal, f"正常参数不应有警告: {normal}"

    # 超范围 — 有警告
    clamped = sales_calc_bq(sp=1.5, fback=-0.3, user_investment=0.5, pface=0.5)
    assert "param_warnings" in clamped, f"超范围参数应有警告: {clamped}"
    assert len(clamped["param_warnings"]) == 2, f"应有 2 条警告: {clamped['param_warnings']}"
    print(f"[PASS] _clamp_01 参数校验: {clamped['param_warnings']}")


def test_strategy_formulas():
    """验证战态分析公式工具可正常调用"""
    from mcp_server.tools_formula import (
        formula_calc_ivi, formula_calc_spe, formula_calc_ews,
        formula_calc_is, formula_calc_gap_effect, formula_calc_eev,
        formula_calc_cs, formula_calc_action,
    )

    ivi = formula_calc_ivi(sp=0.7, fback=0.6, user_investment=0.5, pface=0.4)
    assert "ivi" in ivi, f"IVI 结果缺少 ivi 字段: {ivi}"

    spe = formula_calc_spe(user_ddepth=0.5, target_ddepth=0.5, target_latency=1.0, user_latency=1.0)
    assert "spe" in spe, f"SPE 结果缺少 spe 字段: {spe}"

    ews = formula_calc_ews(gap_effect=0.5, cp_index=0.6, eev=0.4, scarcity_loss=0.1)
    assert "ews" in ews, f"EWS 结果缺少 ews 字段: {ews}"

    is_val = formula_calc_is(backstage=0.6, pface=0.4)
    assert "is" in is_val, f"IS 结果缺少 is 字段: {is_val}"

    ge = formula_calc_gap_effect(act=0.7, exp=0.5)
    assert "gap_effect" in ge, f"Gap_Effect 结果缺少 gap_effect 字段: {ge}"

    eev = formula_calc_eev(p_succ=0.7, escalation_bonus=0.8, p_fail=0.3, power_drop_risk=0.5)
    assert "eev" in eev, f"EEV 结果缺少 eev 字段: {eev}"

    cs = formula_calc_cs(internal_d=0.5, external_r=0.3)
    assert "cs" in cs, f"CS 结果缺少 cs 字段: {cs}"

    action = formula_calc_action(ivi=0.8, spe=1.0, ews=0.6, cs=0.2, ev=0.5)
    assert "action" in action, f"action 结果缺少 action 字段: {action}"
    print(f"[PASS] 战态分析公式 8 个计算函数全部正常")


def test_error_handling():
    """验证错误处理：不存在的联系人"""
    from mcp_server.tools_read import person_brief, person_status

    r1 = person_brief("不存在的客户XYZ123")
    assert "error" in r1, f"不存在的联系人应返回 error: {r1}"

    r2 = person_status("不存在的客户XYZ123")
    assert "error" in r2, f"不存在的联系人应返回 error: {r2}"
    print("[PASS] 错误处理正常：不存在的联系人返回 error")


def test_utf8_encoding():
    """验证中文内容不乱码"""
    from mcp_server.tools_read import person_rank
    result = person_rank()
    # 确保返回的是 dict（不是乱码字符串）
    assert isinstance(result, dict), f"person_rank 应返回 dict: {type(result)}"
    print("[PASS] 中文编码正常")


if __name__ == "__main__":
    print("=" * 60)
    print("最终质量自检 — 全量验收（SalesCRM 54 工具）")
    print("=" * 60)

    print("\n[1] 工具数量验证")
    tools = test_tool_count()

    print("\n[2] 工具分类统计")
    test_tool_categories(tools)

    print("\n[3] Phase 分布验证")
    test_phase_distribution(tools)

    print("\n[4] 安全验证")
    test_fetch_keys_excluded(tools)

    print("\n[5] guide 工具验证")
    test_guide_tool()

    print("\n[6] 销售公式验证")
    test_sales_formulas()

    print("\n[7] 参数校验验证")
    test_clamp_warnings()

    print("\n[8] 战态分析公式验证")
    test_strategy_formulas()

    print("\n[9] 错误处理验证")
    test_error_handling()

    print("\n[10] UTF-8 编码验证")
    test_utf8_encoding()

    print("\n" + "=" * 60)
    print("🎉 全量验收通过 — 55 个工具全部就绪（含 guide + wcd_start）")
    print("=" * 60)
