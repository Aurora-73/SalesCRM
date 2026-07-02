"""辅助参考公式（chat-skills 遗产，标注 Wiki 依据做软关联）。

销售专属公式：BQ / BSP / BWS / PV / sales_action

定位：辅助参考视角，Agent 核验而非套用。阈值是参考，不是硬规则。
Wiki 依据（部分公式已标注，未标注的待 Wiki 补齐）：
    - BQ → [[购买意向指标]]
    - BSP → [[框架]]
    - BWS → [[窗口识别]]
    - PV / sales_action → 无对应 Wiki 条目，未标注

用法：
    from engine.formulas_sales import sales_bq, sales_bsp, sales_bws, sales_action

    bq = sales_bq(sp=0.7, fback=0.8, user_investment=0.3, pface=0.4)
    bsp = sales_bsp(user_ddepth=0.6, target_ddepth=0.5, target_latency=1.2, user_latency=0.8)
    bws = sales_bws(gap_effect=0.3, cp_index=0.5, eev=0.4, scarcity_loss=0.1)
    action = sales_action(bq=bq["bq"], bsp=bsp["bsp"], bws=bws["bws"])
"""

from __future__ import annotations

import sqlite3

from engine.formulas import _validate_params


def sales_params(name: str, conn: "sqlite3.Connection | None" = None) -> dict | str:
    """从数据库自动计算销售决策公式所需的全部可量化参数。

    返回 dict：
        auto: 可自动计算的参数（从 metrics 推导）
        manual: 需要 Agent 判断的参数（附提示）
        raw_metrics: 原始指标值
    """
    from engine.config import load_config
    from engine.importers.db_init import get_db
    from engine.identity import resolve_contact
    from engine.analyzers.metrics import compute_metrics_for_contact

    _conn = conn
    _own_conn = conn is None
    config = load_config()
    if _conn is None:
        _conn = get_db(config.db_path)
    try:
        result = resolve_contact(_conn, name)
        if not result.person:
            return f"未找到客户: {name}"
        person = result.person
        if not person.accounts:
            return f"未找到客户: {name}"

        wxid = person.accounts[0].conversation_id or person.accounts[0].wxid
        m = compute_metrics_for_contact(_conn, config, wxid, person.display_name)

        fback_norm = m.fback.normalized
        fback_quality = m.fback_quality.normalized
        rlatency_norm = m.rlatency.normalized
        qscore_p = m.qscore_personal.normalized
        neediness = m.neediness_penalty
        msg_count = m.msg_count.raw
        active_days = m.active_days.raw
        msg_vol_trend = m.msg_volume_trend.raw
        latency_trend = m.latency_trend.raw

        sp = round(max(0.1, min(1.0, qscore_p * 1.5 + fback_quality * 0.3)), 2)
        user_investment = round(max(0.1, 1.0 - neediness), 2)

        return {
            "person": person.display_name,
            "person_id": person.id,
            "auto": {
                "Sp": sp,
                "Fback": round(fback_norm, 2),
                "Fback_quality": round(fback_quality, 2),
                "Rlatency": round(rlatency_norm, 2),
                "User_Investment": user_investment,
                "Msg_Count": msg_count,
                "Active_Days": active_days,
                "Msg_Volume_Trend": round(msg_vol_trend, 2),
                "Latency_Trend": round(latency_trend, 2),
            },
            "manual": {
                "Pface": {
                    "hint": "客户隐藏真实预算或需求的程度。看客户是否回避报价、含糊其辞",
                    "range": "0.1-0.9",
                    "default": 0.5,
                },
                "User_Ddepth": {
                    "hint": "销售的急迫程度：你是否表现出急于成交、频繁主动联系",
                    "range": "0.1-0.9",
                    "default": 0.5,
                },
                "Target_Ddepth": {
                    "hint": "客户的紧迫程度：客户对解决问题的迫切性",
                    "range": "0.1-0.9",
                    "default": 0.5,
                },
                "Budget_Known": {
                    "hint": "预算是否已明确：客户是否透露过预算范围",
                    "range": "0-1",
                    "default": 0,
                },
                "Decision_Chain": {
                    "hint": "决策链完整度：是否接触到了关键决策人（0=未接触决策人, 1=已接触）",
                    "range": "0.0-1.0",
                    "default": 0.5,
                },
                "Competition": {
                    "hint": "竞争强度：已知竞对数量（0=无, 0.5=1家, 1=多家）",
                    "range": "0.0-1.0",
                    "default": 0.3,
                },
                "Urgency": {
                    "hint": "采购急迫度：客户计划购买时间（0.1=不着急, 0.9=立即）",
                    "range": "0.1-0.9",
                    "default": 0.5,
                },
                "P_succ": {
                    "hint": "成交成功概率：预估报价或推进的成功率",
                    "range": "0.0-1.0",
                    "default": 0.5,
                },
                "P_fail": {
                    "hint": "失败风险：动作失败导致客户流失的概率",
                    "range": "0.0-1.0",
                    "default": 0.3,
                },
            },
            "raw_metrics": {
                "composite": round(m.composite, 4),
                "base_score": round(m.base_score, 4),
                "signal_level": m.signal_level,
                "neediness_penalty": round(neediness, 2),
                "interaction_pattern": m.interaction_pattern,
            },
        }
    finally:
        if _own_conn:
            _conn.close()


def sales_bq(
    sp: float,
    fback: float,
    user_investment: float,
    pface: float,
) -> dict:
    """BQ — 购买意愿真实度（Buyer Intent）。参考视角，不机械套用阈值。

    Wiki 依据: [[购买意向指标]]

    BQ = Sp × 0.3 + Fback × 0.2 + User_Investment × 0.3 + (1 - Pface) × 0.2

    阈值：
        BQ > 1.0：真实购买意向
        BQ < 0.5：大概率在敷衍
    """
    err = _validate_params(sp=sp, fback=fback, user_investment=user_investment, pface=pface)
    if err:
        return {"bq": 0.0, "interpretation": f"参数错误: {err}", "action": "检查输入", "components": {}}

    bq = sp * 0.3 + fback * 0.2 + user_investment * 0.3 + (1 - pface) * 0.2

    if bq > 1.0:
        interpretation = "强烈购买信号：客户的行为投入远超表面。可以主动推进报价。"
        action = "加速推进：准备报价或逼单"
    elif bq > 0.7:
        interpretation = "真实购买意向：客户有明确需求，正在认真评估。"
        action = "持续跟进：提供更多价值，建立信任"
    elif bq > 0.5:
        interpretation = "中性区间：有一定意向但不够强烈。需要更多价值展示。"
        action = "培育：了解需求，展示差异化优势"
    else:
        interpretation = "真实没戏：行为和言语双重冷淡。可能在敷衍或被竞对抢走。"
        action = "降温：减少主动，观察后续反应"

    return {
        "bq": round(bq, 3),
        "interpretation": interpretation,
        "action": action,
        "components": {
            "Sp": sp, "Fback": fback,
            "User_Investment": user_investment, "Pface": pface,
        },
    }


def sales_bsp(
    user_ddepth: float,
    target_ddepth: float,
    target_latency: float,
    user_latency: float,
) -> dict:
    """BSP — 商务势能（Business Social Potential）。参考视角，不机械套用阈值。

    Wiki 依据: [[框架]]

    BSP = (User_Ddepth / Target_Ddepth) × (Target_Latency / User_Latency)

    阈值：
        0.8 < BSP < 1.5：健康商务关系，平等对话
        BSP < 0.6：销售过于被动或被客户牵着走
    """
    err = _validate_params(user_ddepth=user_ddepth, target_ddepth=target_ddepth,
                           target_latency=target_latency, user_latency=user_latency)
    if err:
        return {"bsp": 0.0, "interpretation": f"参数错误: {err}", "action": "检查输入", "components": {}}

    dd_ratio = user_ddepth / max(target_ddepth, 0.01)
    lat_ratio = target_latency / max(user_latency, 0.01)
    bsp = dd_ratio * lat_ratio
    bsp = max(0.01, min(10.0, bsp))

    if bsp < 0.6:
        interpretation = "高危低位：你在商务博弈中处于绝对劣势。客户掌握主动权，你可能在过度被动。"
        action = "红线阻断：立即停止频繁跟进，重建专业形象"
    elif bsp < 0.8:
        interpretation = "偏低：势能略低于客户。需要减少主动、拉长回复间隔。"
        action = "防守：降低联系频率，保留信息，制造不可预测性"
    elif bsp <= 1.5:
        interpretation = "健康均势：双方势能对等，正常商务沟通。"
        action = "维持：保持当前节奏，用价值展示建立优势"
    elif bsp <= 2.0:
        interpretation = "偏高：你的势能高于客户。可以适度释放善意推进合作。"
        action = "推进：适当展示真诚，避免让客户觉得你太冷"
    else:
        interpretation = "过度高位：你可能太冷了，客户可能退缩。"
        action = "降压：主动释放一些善意信号，平衡势能"

    return {
        "bsp": round(bsp, 3),
        "interpretation": interpretation,
        "action": action,
        "components": {
            "User_Ddepth": user_ddepth, "Target_Ddepth": target_ddepth,
            "Target_Latency": target_latency, "User_Latency": user_latency,
        },
    }


def sales_bws(
    gap_effect: float,
    cp_index: float,
    eev: float,
    scarcity_loss: float,
) -> dict:
    """BWS — 购买意向期（Buying Window Signal）。参考视角，不机械套用阈值。

    Wiki 依据: [[窗口识别]]

    BWS = (Gap_Effect * Cp_Index) + EEV - Scarcity_Loss

    阈值：
        BWS > 0.8：出击信号，适合报价/逼单
        BWS < 0.3：意向关闭，不宜强推
    """
    err = _validate_params(gap_effect=gap_effect, cp_index=cp_index, eev=eev, scarcity_loss=scarcity_loss)
    if err:
        return {"bws": 0.0, "interpretation": f"参数错误: {err}", "action": "检查输入", "components": {}}

    bws = (gap_effect * cp_index) + eev - scarcity_loss
    bws = max(-1.0, bws)

    if bws > 0.8:
        interpretation = "出击信号：意向大开。客户的兴趣被调动、配合度已建立、期望值高。"
        action = "立刻行动：发起报价或逼单"
    elif bws > 0.5:
        interpretation = "意向半开：有基础但不够稳固。继续制造价值展示。"
        action = "继续积累：提供更多案例，等待 BWS 突破 0.8"
    elif bws > 0.3:
        interpretation = "意向微开：互动有来有往但缺乏张力。"
        action = "制造波动：打破舒适区，引入新话题或案例"
    else:
        interpretation = "意向关闭：久聊无情绪起伏，稀缺性损耗严重。"
        action = "重置：暂停主动联系（3-7天），用价值内容重新触达"

    return {
        "bws": round(bws, 3),
        "interpretation": interpretation,
        "action": action,
        "components": {
            "Gap_Effect": gap_effect, "Cp_Index": cp_index,
            "EEV": eev, "Scarcity_Loss": scarcity_loss,
        },
    }


def sales_pv(
    p_succ: float,
    escalation_bonus: float,
    p_fail: float,
    loss_risk: float,
) -> dict:
    """PV — 成交期望值（Proposal Value）。参考视角，不机械套用阈值。

    PV = p_succ × escalation_bonus - p_fail × loss_risk

    阈值：
        PV > 0.3：值得推进报价或逼单
    """
    err = _validate_params(p_succ=p_succ, escalation_bonus=escalation_bonus,
                           p_fail=p_fail, loss_risk=loss_risk)
    if err:
        return {"pv": 0.0, "interpretation": f"参数错误: {err}", "components": {}}

    pv = (p_succ * escalation_bonus) - (p_fail * loss_risk)
    pv = max(-1.0, pv)

    if pv > 0.3:
        interpretation = "高期望值：收益远大于风险。值得出手报价。"
    elif pv > 0:
        interpretation = "正期望值：收益略大于风险。可以尝试但需有兜底方案。"
    else:
        interpretation = "负期望值：风险大于收益。不建议当前报价，先积累更多正面信号。"

    return {
        "pv": round(pv, 3),
        "interpretation": interpretation,
        "components": {
            "P_succ": p_succ, "Escalation_Bonus": escalation_bonus,
            "P_fail": p_fail, "Loss_Risk": loss_risk,
        },
    }


def sales_action(bq: float, bsp: float, bws: float, bs: float = 0.0, pv: float = 0.5) -> dict:
    """销售行动决策 — 基于 BQ/BSP/BWS 的策略分发。参考视角，不机械套用阈值。

    返回：
        "bargain": 报价/逼单
        "push": 推进（约见/方案展示）
        "nurture": 培育（解决顾虑，强化价值）
        "reset": 重置关系（换触达方式/换对接人）
        "maintain": 维持（保持存在感）
    """
    err = _validate_params(bq=bq, bsp=bsp, bws=bws, bs=bs, pv=pv)
    if err:
        return {"action": "未知", "reason": f"参数错误: {err}", "instructions": ["检查输入"], "priority": "错误"}

    if bsp < 0.6:
        return {
            "action": "reset",
            "reason": f"BSP={bsp:.2f} < 0.6，销售过于被动",
            "instructions": [
                "立即停止频繁跟进和无效沟通",
                "断联 3-7 天，重建专业形象",
                "恢复后用极简回复，提供价值为主",
                "展示成功案例和客户见证",
            ],
            "priority": "紧急",
        }

    if bq < 0.5:
        return {
            "action": "reset",
            "reason": f"BQ={bq:.2f} < 0.5，客户意向很低",
            "instructions": [
                "停止主动推销，转为被动等待",
                "降低优先级，转向其他高意向客户",
                "如果想保留联系，切换到纯价值提供模式",
            ],
            "priority": "止损",
        }

    if bq > 1.0 and bws > 0.8 and pv > 0.3:
        return {
            "action": "bargain",
            "reason": f"BQ={bq:.2f} > 1.0 且 BWS={bws:.2f} > 0.8 且 PV={pv:.2f} > 0.3，适合报价",
            "instructions": [
                "发起报价或逼单",
                "准备好竞品对比和差异化优势",
                "设定明确的成交时间节点",
            ],
            "priority": "现在",
        }

    if bq > 0.7 and bsp >= 0.6:
        return {
            "action": "push",
            "reason": f"BQ={bq:.2f} > 0.7 且 BSP={bsp:.2f} >= 0.6，适合推进",
            "instructions": [
                "推进约见或方案展示",
                "确认客户需求和决策链",
                "引入成功案例增加信任",
            ],
            "priority": "可以出手",
        }

    if bs > 0 and bws > 0.5:
        return {
            "action": "nurture",
            "reason": f"BS={bs:.2f} > 0 且 BWS={bws:.2f} > 0.5，客户有顾虑",
            "instructions": [
                "深度了解客户顾虑和痛点",
                "提供针对性解决方案",
                "强化价值展示，降低决策风险",
            ],
            "priority": "培育",
        }

    return {
        "action": "maintain",
        "reason": f"BQ={bq:.2f}, BSP={bsp:.2f}, BWS={bws:.2f}，无明确信号",
        "instructions": [
            "保持当前节奏",
            "继续观察信号变化",
            "等待更明确的 BQ 或 BWS 突破",
            "定期发送价值内容保持存在感",
        ],
        "priority": "观察",
    }
