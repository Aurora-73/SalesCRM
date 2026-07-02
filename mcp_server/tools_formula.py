"""MCP 公式工具函数（Phase 3 P3）。

包含两类公式：
1. 战态分析公式（9 个）：IVI/SPE/EWS/IS/Gap_Effect/EEV/CS/action
2. 销售决策公式（6 个）：BQ/BSP/BWS/PV/sales_action — SalesCRM 独有

纯计算函数，零副作用。formula_params/sales_params 读取数据库，其余为纯计算。
参数校验：所有输入参数 clamp 到 [0, 1] 范围，超出范围的值自动截断并标注。
例外：action 类函数的输入是公式结果（可能超 [0,1]），不 clamp。
"""

from engine.formulas import (
    formula_params as _formula_params,
    formula_ivi as _formula_ivi,
    formula_spe as _formula_spe,
    formula_ews as _formula_ews,
    formula_is as _formula_is,
    formula_gap_effect as _formula_gap_effect,
    formula_eev as _formula_eev,
    formula_cs as _formula_cs,
    formula_action as _formula_action,
    sales_params as _sales_params,
    sales_bq as _sales_bq,
    sales_bsp as _sales_bsp,
    sales_bws as _sales_bws,
    sales_pv as _sales_pv,
    sales_action as _sales_action,
)


def _clamp_01(value: float, name: str) -> tuple[float, list[str]]:
    """将参数 clamp 到 [0, 1] 范围，返回 (clamped_value, warnings)。"""
    warnings: list[str] = []
    if value < 0.0:
        warnings.append(f"{name}={value} < 0，已 clamp 到 0")
        return 0.0, warnings
    if value > 1.0:
        warnings.append(f"{name}={value} > 1，已 clamp 到 1")
        return 1.0, warnings
    return value, warnings


def _clamp_params(params: dict) -> tuple[dict, list[str]]:
    """批量 clamp 参数，返回 (clamped_params, all_warnings)。"""
    clamped = {}
    all_warnings: list[str] = []
    for k, v in params.items():
        cv, warns = _clamp_01(v, k)
        clamped[k] = cv
        all_warnings.extend(warns)
    return clamped, all_warnings


# ── 战态分析公式（9 个）──────────────────────────────────────────


def formula_get_params(name: str) -> dict:
    """获取公式参数（从数据库自动计算）。

    什么时候用：需要获取某人的战态分析公式参数时。
    返回什么：dict 含 auto（自动参数）和 manual（需 Agent 判断的参数）。
    边界是什么：name 必填；返回的 manual 参数需要 Agent 结合上下文判断。
    """
    try:
        result = _formula_params(name)
        if isinstance(result, str):
            return {"error": "PERSON_NOT_FOUND", "message": result, "suggestion": "请检查联系人姓名是否正确"}
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查联系人姓名是否正确"}


def formula_calc_ivi(sp: float, fback: float, user_investment: float, pface: float) -> dict:
    """计算 IVI（意图真实度）。

    什么时候用：需要判断对方的合作意向是否真实时。
    返回什么：dict 含 ivi 值和解读。>1.0 真实意向，<0.5 意向薄弱。
    边界是什么：四个参数均为 0-1 浮点数，超出范围自动 clamp。sp=社交势能, fback=反馈率, user_investment=你的投入, pface=公开面具。
    """
    try:
        clamped, warns = _clamp_params({"sp": sp, "fback": fback, "user_investment": user_investment, "pface": pface})
        result = _formula_ivi(**clamped)
        if isinstance(result, dict):
            if warns:
                result["param_warnings"] = warns
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查参数范围（0-1）"}


def formula_calc_spe(user_ddepth: float, target_ddepth: float, target_latency: float, user_latency: float) -> dict:
    """计算 SPE（社交势能）。

    什么时候用：需要评估关系中的权力平衡时。
    返回什么：dict 含 spe 值和解读。0.8-1.5 健康，<0.6 红线阻断。
    边界是什么：四个参数为深度和延迟的归一化值，超出范围自动 clamp。
    """
    try:
        clamped, warns = _clamp_params({
            "user_ddepth": user_ddepth, "target_ddepth": target_ddepth,
            "target_latency": target_latency, "user_latency": user_latency,
        })
        result = _formula_spe(**clamped)
        if isinstance(result, dict) and warns:
            result["param_warnings"] = warns
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查参数范围"}


def formula_calc_ews(gap_effect: float, cp_index: float, eev: float, scarcity_loss: float) -> dict:
    """计算 EWS（推进窗口期）。

    什么时候用：需要判断是否到了推进的最佳时机时。
    返回什么：dict 含 ews 值和解读。>0.8 出击信号，<0.3 窗口关闭。
    边界是什么：四个参数为情绪落差、CP指数、推进期望值、稀缺性损失，超出范围自动 clamp。
    """
    try:
        clamped, warns = _clamp_params({
            "gap_effect": gap_effect, "cp_index": cp_index,
            "eev": eev, "scarcity_loss": scarcity_loss,
        })
        result = _formula_ews(**clamped)
        if isinstance(result, dict) and warns:
            result["param_warnings"] = warns
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查参数范围"}


def formula_calc_is(backstage: float, pface: float) -> dict:
    """计算 IS（真实合作度）。

    什么时候用：需要评估对方愿意暴露真实自我的程度时。
    返回什么：dict 含 is 值和解读。>0.5 高合作度。
    边界是什么：backstage=后台暴露度，pface=公开面具，超出范围自动 clamp。
    """
    try:
        clamped, warns = _clamp_params({"backstage": backstage, "pface": pface})
        result = _formula_is(**clamped)
        if isinstance(result, dict) and warns:
            result["param_warnings"] = warns
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查参数范围"}


def formula_calc_gap_effect(act: float, exp: float) -> dict:
    """计算 Gap_Effect（情绪落差刺激）。

    什么时候用：需要评估互动策略的情绪落差效果时。
    返回什么：dict 含 gap_effect 值和解读。
    边界是什么：act=实际行为强度，exp=预期强度，超出范围自动 clamp。
    """
    try:
        clamped, warns = _clamp_params({"act": act, "exp": exp})
        result = _formula_gap_effect(**clamped)
        if isinstance(result, dict) and warns:
            result["param_warnings"] = warns
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查参数范围"}


def formula_calc_eev(p_succ: float, escalation_bonus: float, p_fail: float, power_drop_risk: float) -> dict:
    """计算 EEV（推进期望值）。

    什么时候用：需要在发起推进动作前评估收益与风险时。
    返回什么：dict 含 eev 值和解读。
    边界是什么：p_succ=成功率，escalation_bonus=推进红利，p_fail=失败率，power_drop_risk=势能降级风险，超出范围自动 clamp。
    """
    try:
        clamped, warns = _clamp_params({
            "p_succ": p_succ, "escalation_bonus": escalation_bonus,
            "p_fail": p_fail, "power_drop_risk": power_drop_risk,
        })
        result = _formula_eev(**clamped)
        if isinstance(result, dict) and warns:
            result["param_warnings"] = warns
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查参数范围"}


def formula_calc_cs(internal_d: float, external_r: float) -> dict:
    """计算 CS（矛盾演化状态）。

    什么时候用：需要评估矛盾积累到临界点的程度时。
    返回什么：dict 含 cs 值和解读。
    边界是什么：internal_d=内在矛盾积累，external_r=外部矛盾释放，超出范围自动 clamp。
    """
    try:
        clamped, warns = _clamp_params({"internal_d": internal_d, "external_r": external_r})
        result = _formula_cs(**clamped)
        if isinstance(result, dict) and warns:
            result["param_warnings"] = warns
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查参数范围"}


def formula_calc_action(ivi: float, spe: float, ews: float, cs: float = 0.0, ev: float = 0.5) -> dict:
    """终极行动决策 — 基于 IVI/SPE/EWS 的策略分发。

    什么时候用：需要综合分析公式得出最终行动建议时。
    返回什么：dict 含 action（推进/拉扯/重置/维持）、reason、instructions。
    边界是什么：ivi/spe/ews 为三大公式结果（范围可能超 [0,1]，不 clamp）；cs=矛盾状态；ev=期望值调整。
    """
    try:
        return _formula_action(ivi=ivi, spe=spe, ews=ews, cs=cs, ev=ev)
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查参数范围"}


# ── 销售决策公式（6 个，SalesCRM 独有）──────────────────────────


def sales_get_params(name: str) -> dict:
    """获取销售公式参数（从数据库自动计算）。

    什么时候用：需要获取某客户的销售决策公式参数时。
    返回什么：dict 含 auto（自动参数）和 manual（需 Agent 判断的参数）。
    边界是什么：name 必填；返回的 manual 参数需要 Agent 结合上下文判断。
    manual 参数包括：Pface/User_Ddepth/Target_Ddepth/Budget_Known/Decision_Chain/
    Competition/Urgency/P_succ/P_fail。
    """
    try:
        result = _sales_params(name)
        if isinstance(result, str):
            return {"error": "PERSON_NOT_FOUND", "message": result, "suggestion": "请检查客户姓名是否正确"}
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查客户姓名是否正确"}


def sales_calc_bq(sp: float, fback: float, user_investment: float, pface: float) -> dict:
    """计算 BQ（购买意愿真实度）。

    什么时候用：需要判断客户的购买意向是否真实时。
    返回什么：dict 含 bq 值和解读。>1.0 强烈购买信号，<0.5 大概率在敷衍。
    边界是什么：四个参数均为 0-1 浮点数，超出范围自动 clamp。
    sp=社交势能, fback=反馈率, user_investment=你的投入, pface=公开面具。
    BQ = Sp×0.3 + Fback×0.2 + User_Investment×0.3 + (1-Pface)×0.2
    """
    try:
        clamped, warns = _clamp_params({"sp": sp, "fback": fback, "user_investment": user_investment, "pface": pface})
        result = _sales_bq(**clamped)
        if isinstance(result, dict) and warns:
            result["param_warnings"] = warns
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查参数范围（0-1）"}


def sales_calc_bsp(user_ddepth: float, target_ddepth: float, target_latency: float, user_latency: float) -> dict:
    """计算 BSP（商务势能）。

    什么时候用：需要评估商务关系中的权力平衡时。
    返回什么：dict 含 bsp 值和解读。0.8-1.5 健康均势，<0.6 高危低位。
    边界是什么：四个参数为深度和延迟的归一化值，超出范围自动 clamp。
    BSP = (User_Ddepth/Target_Ddepth) × (Target_Latency/User_Latency)
    """
    try:
        clamped, warns = _clamp_params({
            "user_ddepth": user_ddepth, "target_ddepth": target_ddepth,
            "target_latency": target_latency, "user_latency": user_latency,
        })
        result = _sales_bsp(**clamped)
        if isinstance(result, dict) and warns:
            result["param_warnings"] = warns
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查参数范围"}


def sales_calc_bws(gap_effect: float, cp_index: float, eev: float, scarcity_loss: float) -> dict:
    """计算 BWS（购买意向期）。

    什么时候用：需要判断是否到了报价/逼单的最佳时机时。
    返回什么：dict 含 bws 值和解读。>0.8 出击信号，<0.3 意向关闭。
    边界是什么：四个参数为情绪落差、CP指数、推进期望值、稀缺性损失，超出范围自动 clamp。
    BWS = (Gap_Effect × Cp_Index) + EEV - Scarcity_Loss
    """
    try:
        clamped, warns = _clamp_params({
            "gap_effect": gap_effect, "cp_index": cp_index,
            "eev": eev, "scarcity_loss": scarcity_loss,
        })
        result = _sales_bws(**clamped)
        if isinstance(result, dict) and warns:
            result["param_warnings"] = warns
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查参数范围"}


def sales_calc_pv(p_succ: float, escalation_bonus: float, p_fail: float, loss_risk: float) -> dict:
    """计算 PV（成交期望值）。

    什么时候用：需要在发起报价或逼单前评估收益与风险时。
    返回什么：dict 含 pv 值和解读。>0.3 值得推进，<0 不建议报价。
    边界是什么：四个参数均为 0-1 浮点数，超出范围自动 clamp。
    p_succ=成交成功概率，escalation_bonus=推进红利，p_fail=失败率，loss_risk=流失风险。
    PV = p_succ × escalation_bonus - p_fail × loss_risk
    """
    try:
        clamped, warns = _clamp_params({
            "p_succ": p_succ, "escalation_bonus": escalation_bonus,
            "p_fail": p_fail, "loss_risk": loss_risk,
        })
        result = _sales_pv(**clamped)
        if isinstance(result, dict) and warns:
            result["param_warnings"] = warns
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查参数范围"}


def sales_calc_action(bq: float, bsp: float, bws: float, bs: float = 0.0, pv: float = 0.5) -> dict:
    """销售行动决策 — 基于 BQ/BSP/BWS 的策略分发。

    什么时候用：需要综合销售公式得出最终行动建议时。
    返回什么：dict 含 action（bargain/push/nurture/reset/maintain）、reason、instructions、priority。
    边界是什么：bq/bsp/bws 为三大公式结果（范围可能超 [0,1]，不 clamp）；bs=顾虑信号；pv=期望值。
    action 类型：
    - bargain: 报价/逼单
    - push: 推进（约见/方案展示）
    - nurture: 培育（解决顾虑，强化价值）
    - reset: 重置关系（换触达方式/换对接人）
    - maintain: 维持（保持存在感）
    """
    try:
        return _sales_action(bq=bq, bsp=bsp, bws=bws, bs=bs, pv=pv)
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查参数范围"}
