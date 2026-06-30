"""战态公式单元测试。

覆盖 IVI/SPE/EWS/IS/CS/Gap_Effect/EEV/Action 各公式的阈值、边界和错误处理。
"""
import math

from engine.formulas import (
    formula_ivi,
    formula_spe,
    formula_ews,
    formula_is,
    formula_gap_effect,
    formula_eev,
    formula_cs,
    formula_action,
)


# ── IVI ──────────────────────────────────────────────────────────────────────

class TestFormulaIVI:
    def test_high_ivi(self):
        """Sp 高 + 投入低 → IVI > 1.0，真实意向。"""
        result = formula_ivi(sp=0.9, fback=0.8, user_investment=0.3, pface=0.3)
        assert result["ivi"] > 1.0
        assert "真实意向" in result["interpretation"] or "强烈" in result["interpretation"]

    def test_low_ivi(self):
        """Sp 低 + 投入高 → IVI < 0.5，真实没戏。"""
        result = formula_ivi(sp=0.1, fback=0.1, user_investment=0.9, pface=0.9)
        assert result["ivi"] < 0.5
        assert "没戏" in result["interpretation"]

    def test_mid_ivi(self):
        """中性区间。"""
        result = formula_ivi(sp=0.5, fback=0.5, user_investment=0.5, pface=0.5)
        assert 0.5 <= result["ivi"] <= 1.0

    def test_division_safety(self):
        """user_investment=0 和 pface=0 不崩溃（分母 min=0.01）。"""
        result = formula_ivi(sp=0.5, fback=0.5, user_investment=0.0, pface=0.0)
        assert isinstance(result["ivi"], float)
        assert result["ivi"] > 0

    def test_fback_zero(self):
        """fback=0 → log(1)=0，IVI=0。"""
        result = formula_ivi(sp=0.5, fback=0.0, user_investment=0.5, pface=0.5)
        assert result["ivi"] == 0.0

    def test_components_preserved(self):
        """返回值包含原始参数。"""
        result = formula_ivi(sp=0.7, fback=0.8, user_investment=0.3, pface=0.4)
        assert result["components"]["Sp"] == 0.7
        assert result["components"]["Fback"] == 0.8

    def test_action_field(self):
        """返回 action 字段。"""
        result = formula_ivi(sp=0.9, fback=0.9, user_investment=0.2, pface=0.2)
        assert "action" in result


# ── SPE ──────────────────────────────────────────────────────────────────────

class TestFormulaSPE:
    def test_healthy_range(self):
        """0.8-1.5 健康均势。"""
        result = formula_spe(user_ddepth=0.5, target_ddepth=0.5,
                             target_latency=1.0, user_latency=1.0)
        assert 0.8 <= result["spe"] <= 1.5
        assert "健康" in result["interpretation"]

    def test_low_spe_red_line(self):
        """SPE < 0.6 高危低位。"""
        result = formula_spe(user_ddepth=0.1, target_ddepth=0.9,
                             target_latency=0.3, user_latency=0.9)
        assert result["spe"] < 0.6
        assert "低位" in result["interpretation"] or "高危" in result["interpretation"]

    def test_high_spe(self):
        """SPE > 2.0 过度高位。"""
        result = formula_spe(user_ddepth=0.9, target_ddepth=0.1,
                             target_latency=0.9, user_latency=0.1)
        assert result["spe"] > 2.0
        assert "过度" in result["interpretation"] or "高位" in result["interpretation"]

    def test_spe_clamp(self):
        """SPE 上限 clamp 到 10.0。"""
        result = formula_spe(user_ddepth=0.9, target_ddepth=0.01,
                             target_latency=0.9, user_latency=0.01)
        assert result["spe"] <= 10.0

    def test_spe_lower_bound(self):
        """SPE 下界 0.01。"""
        result = formula_spe(user_ddepth=0.01, target_ddepth=0.9,
                             target_latency=0.01, user_latency=0.9)
        assert result["spe"] >= 0.01


# ── EWS ──────────────────────────────────────────────────────────────────────

class TestFormulaEWS:
    def test_high_ews(self):
        """EWS > 0.8 出击信号。"""
        result = formula_ews(gap_effect=0.5, cp_index=0.8, eev=0.5, scarcity_loss=0.0)
        assert result["ews"] > 0.8
        assert "出击" in result["interpretation"]

    def test_low_ews(self):
        """EWS < 0.3 意向关闭。"""
        result = formula_ews(gap_effect=-0.2, cp_index=0.1, eev=0.0, scarcity_loss=0.3)
        assert result["ews"] < 0.3
        assert "关闭" in result["interpretation"] or "重置" in result["action"]

    def test_mid_ews(self):
        """0.3-0.8 意向微开或半开。"""
        # EWS = (0.4 * 0.8) + 0.3 - 0.1 = 0.32 + 0.3 - 0.1 = 0.52
        result = formula_ews(gap_effect=0.4, cp_index=0.8, eev=0.3, scarcity_loss=0.1)
        assert 0.3 < result["ews"] < 0.8

    def test_negative_ews_clamp(self):
        """EWS 下界保护 max(-1.0)。"""
        result = formula_ews(gap_effect=-0.9, cp_index=0.0, eev=-0.9, scarcity_loss=0.5)
        assert result["ews"] >= -1.0


# ── IS ───────────────────────────────────────────────────────────────────────

class TestFormulaIS:
    def test_high_intimacy(self):
        """高需求暴露 + 低预算阻力 → 高需求度。"""
        result = formula_is(backstage=0.8, pface=0.2)
        assert result["is"] > 0.5
        assert "高需求度" in result["interpretation"]

    def test_low_intimacy(self):
        """低需求暴露 + 高预算阻力 → 低需求度。"""
        result = formula_is(backstage=0.1, pface=0.9)
        assert result["is"] < 0.3
        assert "低需求度" in result["interpretation"]


# ── Gap Effect ────────────────────────────────────────────────────────────────

class TestFormulaGapEffect:
    def test_positive_gap(self):
        """Act > Exp → 正向落差。"""
        result = formula_gap_effect(act=0.8, exp=0.4)
        assert result["gap_effect"] > 0
        assert "正向" in result["interpretation"]

    def test_negative_gap(self):
        """Act < Exp → 负向落差。"""
        result = formula_gap_effect(act=0.2, exp=0.7)
        assert result["gap_effect"] < 0
        assert "负向" in result["interpretation"]


# ── EEV ──────────────────────────────────────────────────────────────────────

class TestFormulaEEV:
    def test_positive_eev(self):
        """收益 > 风险 → 高期望值。"""
        result = formula_eev(p_succ=0.8, escalation_bonus=0.7,
                             p_fail=0.2, power_drop_risk=0.3)
        assert result["eev"] > 0
        assert "期望值" in result["interpretation"]

    def test_negative_eev(self):
        """风险 > 收益 → 负期望值。"""
        result = formula_eev(p_succ=0.2, escalation_bonus=0.3,
                             p_fail=0.8, power_drop_risk=0.7)
        assert result["eev"] < 0
        assert "负期望值" in result["interpretation"] or "风险" in result["interpretation"]

    def test_eev_lower_bound(self):
        """EEV 下界保护 max(-1.0)。"""
        result = formula_eev(p_succ=0.0, escalation_bonus=0.0,
                             p_fail=1.0, power_drop_risk=1.0)
        assert result["eev"] >= -1.0


# ── CS ───────────────────────────────────────────────────────────────────────

class TestFormulaCS:
    def test_desire_dominates(self):
        """Internal_D > External_R → 欲望主导。"""
        result = formula_cs(internal_d=0.8, external_r=0.3)
        assert result["cs"] > 0
        assert "欲望" in result["interpretation"]

    def test_resistance_dominates(self):
        """External_R > Internal_D → 阻力主导。"""
        result = formula_cs(internal_d=0.2, external_r=0.7)
        assert result["cs"] < 0
        assert "阻力" in result["interpretation"]


# ── Action ────────────────────────────────────────────────────────────────────

class TestFormulaAction:
    def test_red_line_spe(self):
        """SPE < 0.6 → 重置（紧急）。"""
        result = formula_action(ivi=1.0, spe=0.5, ews=0.9)
        assert result["action"] == "重置"
        assert result["priority"] == "紧急"

    def test_red_line_ivi(self):
        """IVI < 0.5 → 重置（止损）。"""
        result = formula_action(ivi=0.3, spe=1.0, ews=0.5)
        assert result["action"] == "重置"
        assert result["priority"] == "止损"

    def test_attack(self):
        """EWS > 0.8 + IVI > 0.8 → 进攻。"""
        result = formula_action(ivi=0.9, spe=1.2, ews=0.9)
        assert result["action"] == "进攻"
        assert result["priority"] == "现在"

    def test_attack_cautious(self):
        """EWS > 0.8 + 0.5 < IVI < 0.8 → 进攻（谨慎）。"""
        result = formula_action(ivi=0.6, spe=1.2, ews=0.9)
        assert "进攻" in result["action"]
        assert "谨慎" in result["action"]

    def test_pull(self):
        """SPE 0.8-1.5 + IVI >= 0.5 + EWS <= 0.8 → 拉锯。"""
        result = formula_action(ivi=0.6, spe=1.0, ews=0.5)
        assert result["action"] == "拉锯"

    def test_maintain(self):
        """默认情况 → 维持。"""
        result = formula_action(ivi=0.7, spe=1.6, ews=0.5)
        assert result["action"] == "维持"

    def test_red_line_takes_priority_over_attack(self):
        """SPE 红线优先于进攻判断。"""
        result = formula_action(ivi=0.9, spe=0.5, ews=0.9)
        assert result["action"] == "重置"

    def test_has_instructions(self):
        """每个结果都有 instructions 列表。"""
        for spe_val in [0.3, 0.7, 1.0, 1.6]:
            result = formula_action(ivi=0.6, spe=spe_val, ews=0.5)
            assert "instructions" in result
            assert len(result["instructions"]) > 0
