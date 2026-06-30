"""公式计算测试。"""
import math
import pytest


class TestValidateParams:
    """_validate_params 边界。"""

    def test_valid(self):
        from engine.formulas import _validate_params
        assert _validate_params(a=1.0, b=0) is None

    def test_string_param(self):
        from engine.formulas import _validate_params
        err = _validate_params(a="abc")
        assert "a" in err
        assert "str" in err

    def test_none_param(self):
        from engine.formulas import _validate_params
        err = _validate_params(a=None)
        assert "NoneType" in err


class TestFormulaIVI:
    def test_normal(self):
        from engine.formulas import formula_ivi
        r = formula_ivi(sp=0.7, fback=0.8, user_investment=0.5, pface=0.4)
        assert r["ivi"] > 0
        assert isinstance(r["interpretation"], str)
        assert isinstance(r["action"], str)

    def test_high_ivi(self):
        from engine.formulas import formula_ivi
        r = formula_ivi(sp=1.0, fback=1.0, user_investment=0.1, pface=0.1)
        assert r["ivi"] > 1.0
        assert "意向" in r["interpretation"]

    def test_low_ivi(self):
        from engine.formulas import formula_ivi
        r = formula_ivi(sp=0.1, fback=0.1, user_investment=0.9, pface=0.9)
        assert r["ivi"] < 0.5
        assert "没戏" in r["interpretation"]

    def test_zero_pface_no_crash(self):
        from engine.formulas import formula_ivi
        r = formula_ivi(sp=0.5, fback=0.5, user_investment=0.5, pface=0.0)
        assert "ivi" in r  # 不应除零

    def test_string_input_rejected(self):
        from engine.formulas import formula_ivi
        r = formula_ivi(sp="abc", fback=0.5, user_investment=0.5, pface=0.5)
        assert "参数错误" in r["interpretation"]


class TestFormulaAction:
    def test_red_line_low_spe(self):
        from engine.formulas import formula_action
        r = formula_action(ivi=0.8, spe=0.3, ews=0.5)
        assert r["action"] == "重置"
        assert r["priority"] == "紧急"

    def test_stop_low_ivi(self):
        from engine.formulas import formula_action
        r = formula_action(ivi=0.2, spe=0.8, ews=0.5)
        assert r["action"] == "重置"
        assert r["priority"] == "止损"

    def test_attack_high_ivi_ews(self):
        from engine.formulas import formula_action
        r = formula_action(ivi=1.0, spe=1.0, ews=1.0)
        assert r["action"] == "进攻"

    def test_pull_medium_ivi_low_ews(self):
        from engine.formulas import formula_action
        r = formula_action(ivi=0.6, spe=1.0, ews=0.3)
        assert r["action"] == "拉锯"

    def test_maintain_neutral(self):
        from engine.formulas import formula_action
        r = formula_action(ivi=0.5, spe=1.0, ews=0.3)
        assert r["action"] == "拉锯"

    def test_string_input_rejected(self):
        from engine.formulas import formula_action
        r = formula_action(ivi="x", spe=1.0, ews=0.5)
        assert "参数错误" in r.get("reason", r.get("reason", ""))


class TestFormulaSPE:
    def test_healthy(self):
        from engine.formulas import formula_spe
        r = formula_spe(user_ddepth=0.5, target_ddepth=0.5, target_latency=1.0, user_latency=1.0)
        assert 0.8 <= r["spe"] <= 1.5
        assert "健康" in r["interpretation"] or "均势" in r["interpretation"]

    def test_red_line(self):
        from engine.formulas import formula_spe
        r = formula_spe(user_ddepth=0.1, target_ddepth=0.9, target_latency=0.5, user_latency=2.0)
        assert r["spe"] < 0.6
        assert "低位" in r["interpretation"] or "红线" in r["interpretation"]


class TestFormulaEWS:
    def test_open_window(self):
        from engine.formulas import formula_ews
        r = formula_ews(gap_effect=0.8, cp_index=0.7, eev=0.5, scarcity_loss=0.1)
        assert r["ews"] > 0.3

    def test_closed_window(self):
        from engine.formulas import formula_ews
        r = formula_ews(gap_effect=0.0, cp_index=0.0, eev=0.0, scarcity_loss=0.5)
        assert r["ews"] < 0.3


class TestFormulaIS:
    def test_high_intimacy(self):
        from engine.formulas import formula_is
        r = formula_is(backstage=0.8, pface=0.2)
        assert r["is"] > 0.5

    def test_low_intimacy(self):
        from engine.formulas import formula_is
        r = formula_is(backstage=0.1, pface=0.9)
        assert r["is"] < 0.2
