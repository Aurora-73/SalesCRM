"""公式工具 — 客户战态分析。

从聊天分析的算法模块提取的核心公式，改为 Agent 可调用的工具。
部分参数从 SQLite 自动计算，部分需要 Agent 根据聊天内容判断。

用法：
    from engine.tools import formula_params, formula_ivi, formula_spe, formula_ews, formula_action

    # 第一步：获取所有可自动计算的参数
    params = formula_params("张三")

    # 第二步：Agent 根据聊天内容补全 manual 参数（Pface/Ddepth 等）
    # 第三步：代入公式计算
    ivi = formula_ivi(sp=0.7, fback=0.8, user_investment=0.3, pface=0.4)
    spe = formula_spe(user_ddepth=0.6, target_ddepth=0.5, target_latency=1.2, user_latency=0.8)
    ews = formula_ews(gap_effect=0.3, cp_index=0.5, eev=0.4, scarcity_loss=0.1)
    action = formula_action(ivi=ivi["ivi"], spe=spe["spe"], ews=ews["ews"])
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta


def _validate_params(**kwargs) -> str | None:
    """校验公式参数类型。返回错误消息或 None。"""
    for name, val in kwargs.items():
        if not isinstance(val, (int, float)):
            return f"{name} 必须是数字，收到 {type(val).__name__}"
    return None


def formula_params(name: str, conn: "sqlite3.Connection | None" = None) -> dict | str:
    """从数据库自动计算 chat-skills 公式所需的全部可量化参数。

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
            return f"未找到联系人: {name}"
        person = result.person
        if not person.accounts:
            return f"未找到联系人: {name}"

        wxid = person.accounts[0].conversation_id or person.accounts[0].wxid
        m = compute_metrics_for_contact(_conn, config, wxid, person.display_name)

        # 从 metrics 推导 chat-skills 参数
        fback_norm = m.fback.normalized
        fback_quality = m.fback_quality.normalized
        rlatency_norm = m.rlatency.normalized
        escore_norm = m.escore.normalized
        escore_vol = m.escore_volatility.normalized
        qscore_p = m.qscore_personal.normalized
        qscore_f = m.qscore_functional.normalized
        neediness = m.neediness_penalty
        msg_count = m.msg_count.raw
        active_days = m.active_days.raw
        msg_vol_trend = m.msg_volume_trend.raw
        latency_trend = m.latency_trend.raw

        # 推导 Sp（显示性偏好）：个人化问题比例 × 回复质量，下限 0.1 避免 IVI 恒为 0
        sp = round(max(0.1, min(1.0, qscore_p * 1.5 + fback_quality * 0.3)), 2)

        # 推导 User_Investment：从 neediness_penalty 反推（neediness 越低 = 我方投入越高）
        user_investment = round(max(0.1, 1.0 - neediness), 2)

        # 推导 S_cost（沉没成本估计）：消息量 + 活跃天数
        s_cost = round(min(1.0, (math.log(1 + msg_count) / math.log(500)) * 0.5 + (active_days / 90) * 0.5), 2)

        # 推导稀缺性损耗：消息量趋势下降 + 延迟趋势变慢 = 稀缺性损耗增加
        scarcity_loss = 0.0
        if msg_vol_trend < 0.8:
            scarcity_loss += (0.8 - msg_vol_trend) * 0.3
        if latency_trend < 0.8:
            scarcity_loss += (0.8 - latency_trend) * 0.2
        scarcity_loss = round(min(0.5, scarcity_loss), 2)

        # 推导 Ve（情绪效价）：从 escore 直接映射
        ve = round(escore_norm, 2)

        # 推导 EV（情绪波动）：从 escore_volatility 直接映射
        ev = round(escore_vol, 2)

        # 推导 Noise（言语掩饰）：敷衍回复比例越高 = noise 越高
        # fback_quality 低 + qscore_f 高 = 大量工具化问题 + 敷衍回复
        noise = round(max(0.0, 1.0 - fback_quality) * 0.5 + qscore_f * 0.3, 2)

        # 推导 Exp（心理预期）：从回复速度趋势推导
        # 如果客户一直在秒回，用户预期就高（exp 高）；如果客户最近变慢，预期被打破
        exp = round(min(1.0, 0.5 + rlatency_norm * 0.3), 2)

        return {
            "person": person.display_name,
            "person_id": person.id,
            "auto": {
                "Sp": sp,
                "Fback": round(fback_norm, 2),
                "Fback_quality": round(fback_quality, 2),
                "Rlatency": round(rlatency_norm, 2),
                "Ve": ve,
                "EV": ev,
                "S_cost": s_cost,
                "Noise": noise,
                "Exp": exp,
                "User_Investment": user_investment,
                "Scarcity_Loss": scarcity_loss,
            },
            "manual": {
                "Pface": {
                    "hint": "预算阻力：客户隐藏真实需求的防备程度。看客户是否回避报价、含糊其辞",
                    "range": "0.1-0.9",
                    "default": 0.5,
                },
                "Ddepth": {
                    "hint": "你的谈判空间：你的信息保留和底线控制。看你是否暴露太多、过于急切",
                    "range": "0.1-0.9",
                    "default": 0.5,
                },
                "Target_Ddepth": {
                    "hint": "客户的谈判空间：客户保留了多少信息、是否有决策自主权",
                    "range": "0.1-0.9",
                    "default": 0.5,
                },
                "Backstage": {
                    "hint": "需求暴露度：客户是否透露了真实痛点和决策优先级",
                    "range": "0.1-0.9",
                    "default": 0.3,
                },
                "Cp_Index": {
                    "hint": "配合度指数：客户对你建议的接受程度。如'安排演示''提供资料'是否配合",
                    "range": "0.0-1.0",
                    "default": 0.3,
                },
                "Internal_D": {
                    "hint": "客户内在需求：客户对解决方案的真实渴望程度",
                    "range": "0.1-0.9",
                    "default": 0.5,
                },
                "External_R": {
                    "hint": "外部阻力：预算限制、内部审批流程、竞品压力等障碍",
                    "range": "0.1-0.9",
                    "default": 0.4,
                },
                "Anx": {
                    "hint": "决策焦虑：客户对采购决策的谨慎程度（高焦虑=偏保守）",
                    "range": "0.1-0.9",
                    "default": 0.4,
                },
                "Def": {
                    "hint": "采购防御：客户面对销售时的自我保护意识",
                    "range": "0.1-0.9",
                    "default": 0.4,
                },
                "Sv": {
                    "hint": "解决方案价值：你提供的产品/服务能解决的问题程度",
                    "range": "0.1-0.9",
                    "default": 0.5,
                },
                "Rv": {
                    "hint": "专业影响力：你的行业经验和专业可信度",
                    "range": "0.1-0.9",
                    "default": 0.5,
                },
                "P_succ": {
                    "hint": "推进成功概率：发起报价/推进的预估成功率",
                    "range": "0.0-1.0",
                    "default": 0.5,
                },
                "P_fail": {
                    "hint": "破裂风险：动作失败导致关系倒退的概率",
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


def formula_ivi(
    sp: float,
    fback: float,
    user_investment: float,
    pface: float,
) -> dict:
    """IVI — 意图真实度指数。

    穿透"反话"和"假性拒绝"，过滤面子客套话。
    IVI = [Sp * log(Fback + 1)] / [User_Investment * Pface]

    阈值：
        IVI > 1.0：行为远超口头表态，真实意向
        IVI < 0.5：真实无意向，立即止损
    """
    err = _validate_params(sp=sp, fback=fback, user_investment=user_investment, pface=pface)
    if err:
        return {"ivi": 0.0, "interpretation": f"参数错误: {err}", "action": "检查输入", "components": {}}
    denominator = max(user_investment * pface, 0.01)
    ivi = (sp * math.log(fback + 1)) / denominator

    # 解读
    if ivi > 1.5:
        interpretation = "强烈意向信号：客户的行为投入远超表面。忽略口头客套，可以主动推进。"
    elif ivi > 1.0:
        interpretation = "真实意向：行为与表态不一致。嘴上可能犹豫但行为在配合，继续推进但注意节奏。"
    elif ivi > 0.5:
        interpretation = "中性区间：有基本互动但不够强烈。需要制造更多情绪波动来拉高 Sp。"
    else:
        interpretation = "真实没戏：行为和言语双重冷淡。建议止损或大幅降低投入重建 Ddepth。"

    # 策略建议
    if ivi > 1.0:
        action = "进攻：可以直接报价或推进测试"
    elif ivi > 0.5:
        action = "拉锯：通过价值展示和节奏控制提高 Sp"
    else:
        action = "重置：停止主动，重建战略纵深"

    return {
        "ivi": round(ivi, 3),
        "interpretation": interpretation,
        "action": action,
        "components": {
            "Sp": sp, "Fback": fback,
            "User_Investment": user_investment, "Pface": pface,
        },
    }


def formula_spe(
    user_ddepth: float,
    target_ddepth: float,
    target_latency: float,
    user_latency: float,
) -> dict:
    """SPE — 社交势能指数。

    监控权力平衡，防止沦为低位。
    SPE = (User_Ddepth / Target_Ddepth) * (Target_Latency / User_Latency)

    阈值：
        0.8 < SPE < 1.5：健康均势
        SPE < 0.6：高危低位，红线阻断
        SPE > 2.0：过度高位，可能让客户退缩
    """
    err = _validate_params(user_ddepth=user_ddepth, target_ddepth=target_ddepth,
                           target_latency=target_latency, user_latency=user_latency)
    if err:
        return {"spe": 0.0, "interpretation": f"参数错误: {err}", "action": "检查输入", "components": {}}
    dd_ratio = user_ddepth / max(target_ddepth, 0.01)
    lat_ratio = target_latency / max(user_latency, 0.01)
    spe = dd_ratio * lat_ratio
    # 参数范围 0.1-0.9，理论最大 ~81，实际 clamp 到 [0.01, 10.0]
    spe = max(0.01, min(10.0, spe))

    if spe < 0.6:
        interpretation = "高危低位：你在谈判中处于绝对劣势。客户掌握主动权，过度跟进风险高。"
        action = "红线阻断：立即停止过度跟进，启动冷却期，重建谈判空间。"
    elif spe < 0.8:
        interpretation = "偏低：谈判势能略低于客户。需要减少跟进频率、拉长回复间隔。"
        action = "防守：降低消息频率，保留信息，制造不可预测性。"
    elif spe <= 1.5:
        interpretation = "健康均势：双方谈判势能对等，正常博弈互动。"
        action = "维持：保持当前节奏，用价值展示制造关注波动。"
    elif spe <= 2.0:
        interpretation = "偏高：你的谈判势能高于客户。可以适度释放善意推进合作。"
        action = "推进：适当展示诚意，避免让客户觉得你太冷淡。"
    else:
        interpretation = "过度高位：你可能太冷淡了，客户可能退缩。"
        action = "降压：主动释放一些善意信号，平衡势能。"

    return {
        "spe": round(spe, 3),
        "interpretation": interpretation,
        "action": action,
        "components": {
            "User_Ddepth": user_ddepth, "Target_Ddepth": target_ddepth,
            "Target_Latency": target_latency, "User_Latency": user_latency,
        },
    }


def formula_ews(
    gap_effect: float,
    cp_index: float,
    eev: float,
    scarcity_loss: float,
) -> dict:
    """EWS — 推进窗口期。

    决定何时发起报价，降低被拒风险。
    EWS = (Gap_Effect * Cp_Index) + EEV - Scarcity_Loss

    阈值：
        EWS > 0.8：出击信号
        EWS < 0.3：意向关闭，需要重新积累
    """
    err = _validate_params(gap_effect=gap_effect, cp_index=cp_index, eev=eev, scarcity_loss=scarcity_loss)
    if err:
        return {"ews": 0.0, "interpretation": f"参数错误: {err}", "action": "检查输入", "components": {}}
    ews = (gap_effect * cp_index) + eev - scarcity_loss
    ews = max(-1.0, ews)  # 下界保护

    if ews > 0.8:
        interpretation = "出击信号：意向大开。客户兴趣被调动、配合度已建立、意向值高。"
        action = "立刻行动：发起报价或安排签约推进。"
    elif ews > 0.5:
        interpretation = "意向半开：有基础但不够稳固。继续用价值展示制造关注落差。"
        action = "继续积累：价值展示 + 配合度测试，等待 EWS 突破 0.8。"
    elif ews > 0.3:
        interpretation = "意向微开：互动有来有往但缺乏成交动力。"
        action = "制造波动：打破常规沟通，引入新价值点或轻微挑战。"
    else:
        interpretation = "意向关闭：久聊无兴趣起伏，稀缺性损耗严重。"
        action = "重置：暂停跟进（3-7天），用案例分享制造关注落差。"

    return {
        "ews": round(ews, 3),
        "interpretation": interpretation,
        "action": action,
        "components": {
            "Gap_Effect": gap_effect, "Cp_Index": cp_index,
            "EEV": eev, "Scarcity_Loss": scarcity_loss,
        },
    }


def formula_is(backstage: float, pface: float) -> dict:
    """IS — 真实需求度。

    IS = Backstage / (Pface + 1.0)
    客户越愿意暴露真实需求（痛点/预算/优先级），成交可能性越高。
    """
    err = _validate_params(backstage=backstage, pface=pface)
    if err:
        return {"is": 0.0, "interpretation": f"参数错误: {err}", "components": {}}
    is_score = backstage / (pface + 1.0)

    if is_score > 0.5:
        interpretation = "高需求度：客户愿意透露真实痛点和决策链。成交可能性高。"
    elif is_score > 0.3:
        interpretation = "中等需求度：有一定信任但仍有防备。继续建立专业信任。"
    else:
        interpretation = "低需求度：客户仍在维持表面沟通。需要更多挖掘和价值展示。"

    return {
        "is": round(is_score, 3),
        "interpretation": interpretation,
        "components": {"Backstage": backstage, "Pface": pface},
    }


def formula_gap_effect(act: float, exp: float) -> dict:
    """Gap_Effect — 情绪落差刺激。

    Gap_Effect = Act - Exp
    制造负向预期差，引发对方主动消除认知失调的冲动。
    """
    err = _validate_params(act=act, exp=exp)
    if err:
        return {"gap_effect": 0.0, "interpretation": f"参数错误: {err}", "components": {}}
    gap = act - exp

    if gap > 0.3:
        interpretation = "正向落差：实际体验超出预期。客户兴趣上升。"
    elif gap > 0:
        interpretation = "微弱正向：略好于预期。互动正常但缺乏突破。"
    elif gap > -0.3:
        interpretation = "微弱负向：略低于预期。可能引发客户的好奇。"
    else:
        interpretation = "强负向落差：远低于预期。可能引发客户退缩，需谨慎。"

    return {
        "gap_effect": round(gap, 3),
        "interpretation": interpretation,
        "components": {"Act": act, "Exp": exp},
    }


def formula_eev(p_succ: float, escalation_bonus: float,
                p_fail: float, power_drop_risk: float) -> dict:
    """EEV — 推进期望值。

    EEV = (P_succ * 推进价值红利) - (P_fail * 势能降级风险)
    发起动作前，计算收益与下行风险的综合期望值。
    """
    err = _validate_params(p_succ=p_succ, escalation_bonus=escalation_bonus,
                           p_fail=p_fail, power_drop_risk=power_drop_risk)
    if err:
        return {"eev": 0.0, "interpretation": f"参数错误: {err}", "components": {}}
    eev = (p_succ * escalation_bonus) - (p_fail * power_drop_risk)
    eev = max(-1.0, eev)  # 下界保护

    if eev > 0.3:
        interpretation = "高期望值：收益远大于风险。值得出手。"
    elif eev > 0:
        interpretation = "正期望值：收益略大于风险。可以尝试但需有兜底方案。"
    else:
        interpretation = "负期望值：风险大于收益。不建议当前推进，先积累更多正面信号。"

    return {
        "eev": round(eev, 3),
        "interpretation": interpretation,
        "components": {
            "P_succ": p_succ, "Escalation_Bonus": escalation_bonus,
            "P_fail": p_fail, "Power_Drop_Risk": power_drop_risk,
        },
    }


def formula_cs(internal_d: float, external_r: float) -> dict:
    """CS — 矛盾演化状态。

    CS = Internal_D - External_R
    量变引起质变，找准临界点推进。
    """
    err = _validate_params(internal_d=internal_d, external_r=external_r)
    if err:
        return {"cs": 0.0, "interpretation": f"参数错误: {err}", "components": {}}
    cs = internal_d - external_r

    if cs > 0.3:
        interpretation = "内在欲望占主导：客户想靠近你，外部阻力已被压过。临界点已到。"
    elif cs > 0:
        interpretation = "微弱倾向：欲望略大于阻力。继续积累正面体验。"
    elif cs > -0.3:
        interpretation = "阻力略大：外部因素（矜持/环境/人设）在压制欲望。减少阻力来源。"
    else:
        interpretation = "阻力主导：外部障碍远大于内在欲望。需要先解决阻力来源。"

    return {
        "cs": round(cs, 3),
        "interpretation": interpretation,
        "components": {"Internal_D": internal_d, "External_R": external_r},
    }


def formula_action(ivi: float, spe: float, ews: float,
                   cs: float = 0.0, ev: float = 0.5) -> dict:
    """终极行动决策 — 基于 IVI/SPE/EWS 的策略分发。

    三种指令：
        进攻：EWS 高 + IVI > 0.8
        拉扯：SPE 平衡 + IVI 及格 + EWS 未满
        重置：SPE < 0.6 或 IVI < 0.5
    """
    err = _validate_params(ivi=ivi, spe=spe, ews=ews)
    if err:
        return {"action": "未知", "reason": f"参数错误: {err}", "instructions": ["检查输入"], "priority": "错误"}
    # 红线检查
    if spe < 0.6:
        return {
            "action": "重置",
            "reason": f"SPE={spe:.2f} < 0.6，高危低位",
            "instructions": [
                "立即停止过度跟进和无效沟通",
                "暂停跟进 3-7 天，重建谈判空间",
                "恢复后用极简回复（提供价值为主）",
                "用案例分享展示专业价值",
            ],
            "priority": "紧急",
        }

    if ivi < 0.5:
        return {
            "action": "重置",
            "reason": f"IVI={ivi:.2f} < 0.5，真实没戏",
            "instructions": [
                "停止额外投入，接受现实",
                "降低优先级，转向其他客户",
                "如果想保留联系，切换到纯商务模式（无推销）",
            ],
            "priority": "止损",
        }

    # 进攻判断
    if ews > 0.8 and ivi > 0.8:
        return {
            "action": "进攻",
            "reason": f"EWS={ews:.2f} > 0.8 且 IVI={ivi:.2f} > 0.8，意向大开",
            "instructions": [
                "发起报价试探（不给具体价格，先试探）",
                "或发起签约推进测试（安排演示/参观）",
                "如果客户配合，立刻推进到具体方案",
            ],
            "priority": "现在",
        }

    if ews > 0.8 and ivi > 0.5:
        return {
            "action": "进攻（谨慎）",
            "reason": f"EWS={ews:.2f} > 0.8 但 IVI={ivi:.2f} 中等",
            "instructions": [
                "发起低风险推进（如：'下周安排一次演示？'）",
                "准备好兜底方案（被拒时如何体面收场）",
                "观察客户的反应再决定下一步",
            ],
            "priority": "可以出手",
        }

    # 拉扯判断
    if 0.8 <= spe <= 1.5 and ivi >= 0.5 and ews <= 0.8:
        instructions = [
            "用价值反差制造关注落差（打破预期）",
            "用节奏控制积累互动深度",
            "用配合度测试提升 Cp_Index",
        ]
        if ev < 0.3:
            instructions.append("当前兴趣平淡，需要引入新价值点或轻微挑战")
        if cs > 0.3:
            instructions.append("关系已到临界点，可以尝试温和推进")

        return {
            "action": "拉锯",
            "reason": f"SPE={spe:.2f} 均势，IVI={ivi:.2f} 及格，EWS={ews:.2f} 未满",
            "instructions": instructions,
            "priority": "继续积累",
        }

    # 默认：维持
    return {
        "action": "维持",
        "reason": f"IVI={ivi:.2f}, SPE={spe:.2f}, EWS={ews:.2f}，无明确信号",
        "instructions": [
            "保持当前节奏",
            "继续观察信号变化",
            "等待更明确的 IVI 或 EWS 突破",
        ],
        "priority": "观察",
    }


# ── 销售决策公式（SalesCRM）─────────────────────────────────────────────

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
    """BQ — 购买意愿真实度（Buyer Intent）。

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
    """BSP — 商务势能（Business Social Potential）。

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
    """BWS — 购买意向期（Buying Window Signal）。

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
    """PV — 成交期望值（Proposal Value）。

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
    """销售行动决策 — 基于 BQ/BSP/BWS 的策略分发。

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
