"""销售阶段自动识别器单元测试。

覆盖 9 个阶段的识别逻辑、停滞判定、推进信号和阻碍识别。
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from engine.analyzers.stage_recognizer import (
    recognize_stage,
    get_stage_summary,
    _classify_stage,
    _get_next_stage,
    _check_stagnant,
    _is_failed,
    _has_event,
)
from engine.models.stage import STAGES, StageState


class TestStageHelpers:
    def test_get_next_stage_normal(self):
        assert _get_next_stage("线索") == "初步接触"
        assert _get_next_stage("深入沟通") == "已会面"
        assert _get_next_stage("方案推进") == "签约确认"

    def test_get_next_stage_terminal(self):
        assert _get_next_stage("签约确认") == ""
        assert _get_next_stage("退出/失败") == ""

    def test_get_next_stage_unknown(self):
        assert _get_next_stage("不存在") == ""

    def test_stages_list_complete(self):
        assert len(STAGES) == 9
        assert STAGES[0] == "未识别"
        assert STAGES[-1] == "退出/失败"


class TestCheckStagnant:
    def test_terminal_not_stagnant(self):
        assert _check_stagnant(999, "签约确认", None) is False
        assert _check_stagnant(999, "退出/失败", None) is False
        assert _check_stagnant(999, "未识别", None) is False

    def test_线索_stagnant_after_7_days(self):
        assert _check_stagnant(8, "线索", None) is True

    def test_线索_not_stagnant_within_7_days(self):
        assert _check_stagnant(5, "线索", None) is False

    def test_深入沟通_stagnant_after_21_days(self):
        assert _check_stagnant(22, "深入沟通", None) is True

    def test_持续跟进_stagnant_after_21_days(self):
        assert _check_stagnant(22, "持续跟进", None) is True

    def test_方案推进_stagnant_after_28_days(self):
        assert _check_stagnant(29, "方案推进", None) is True


class TestClassifyStage:
    def _setup_tables(self, tmp_db):
        tmp_db.execute("CREATE TABLE IF NOT EXISTS failure_archives (contact_wxid TEXT PRIMARY KEY)")
        tmp_db.execute("CREATE TABLE IF NOT EXISTS events (contact_wxid TEXT, event_type TEXT)")
        tmp_db.commit()

    def test_no_messages_unrecognized(self, tmp_db):
        self._setup_tables(tmp_db)
        from engine.models.metrics import Metrics, MetricValue
        metrics = Metrics(composite=0.0, recent=MetricValue(raw=999))
        stage, signals, blockers = _classify_stage(tmp_db, metrics, "wxid_test")
        assert stage == "未识别"

    def test_recent_activity_线索(self, tmp_db):
        self._setup_tables(tmp_db)
        from engine.models.metrics import Metrics, MetricValue
        metrics = Metrics(composite=0.2, recent=MetricValue(raw=10))
        stage, signals, blockers = _classify_stage(tmp_db, metrics, "wxid_test")
        assert stage == "线索"

    def test_low_score_初步接触(self, tmp_db):
        self._setup_tables(tmp_db)
        from engine.models.metrics import Metrics, MetricValue
        metrics = Metrics(composite=0.4, recent=MetricValue(raw=5))
        stage, signals, blockers = _classify_stage(tmp_db, metrics, "wxid_test")
        assert stage == "初步接触"

    def test_medium_score_深入沟通(self, tmp_db):
        self._setup_tables(tmp_db)
        from engine.models.metrics import Metrics, MetricValue
        metrics = Metrics(composite=0.6, recent=MetricValue(raw=2))
        stage, signals, blockers = _classify_stage(tmp_db, metrics, "wxid_test")
        assert stage == "深入沟通"

    def test_high_score_方案推进(self, tmp_db):
        self._setup_tables(tmp_db)
        from engine.models.metrics import Metrics, MetricValue
        tmp_db.execute("INSERT INTO events (contact_wxid, event_type) VALUES (?, ?)", ("wxid_test", "meeting"))
        tmp_db.commit()
        metrics = Metrics(composite=0.8, recent=MetricValue(raw=1))
        stage, signals, blockers = _classify_stage(tmp_db, metrics, "wxid_test")
        assert stage == "方案推进"

    def test_failed_stage(self, tmp_db):
        self._setup_tables(tmp_db)
        from engine.models.metrics import Metrics, MetricValue
        tmp_db.execute("INSERT INTO failure_archives (contact_wxid) VALUES (?)", ("wxid_failed",))
        tmp_db.commit()
        metrics = Metrics(composite=0.8, recent=MetricValue(raw=1))
        stage, signals, blockers = _classify_stage(tmp_db, metrics, "wxid_failed")
        assert stage == "退出/失败"
        assert "失败" in blockers[0]


class TestGetStageSummary:
    def test_summary_contains_all_fields(self):
        from engine.models.stage import Stage, StageState
        stage = Stage(stage_state=StageState(
            current_stage="深入沟通",
            days_in_current_stage=5,
            is_stagnant=False,
            next_stage="已会面",
            advancement_signals=["客户主动发起"],
            blockers=[],
        ))
        summary = get_stage_summary(stage)
        assert summary["current_stage"] == "深入沟通"
        assert summary["stage_index"] == STAGES.index("深入沟通")
        assert summary["days_in_current_stage"] == 5
        assert summary["is_stagnant"] is False
        assert summary["next_stage"] == "已会面"
        assert summary["advancement_signals"] == ["客户主动发起"]
        assert summary["blockers"] == []


class TestStageStateModel:
    def test_stage_state_to_dict(self):
        s = StageState(
            current_stage="深入沟通",
            next_stage="已会面",
            entered_at="2026-06-01",
            days_in_current_stage=10,
            is_stagnant=False,
            advancement_signals=["信号1"],
            blockers=["阻碍1"],
        )
        d = s.to_dict()
        assert d["current_stage"] == "深入沟通"
        assert d["next_stage"] == "已会面"
        assert d["advancement_signals"] == ["信号1"]
        assert d["blockers"] == ["阻碍1"]

    def test_stage_state_from_dict(self):
        d = {
            "current_stage": "方案推进",
            "next_stage": "签约确认",
            "entered_at": "2026-06-01",
            "days_in_current_stage": 15,
            "is_stagnant": False,
            "advancement_signals": ["a"],
            "blockers": ["b"],
        }
        s = StageState.from_dict(d)
        assert s.current_stage == "方案推进"
        assert s.days_in_current_stage == 15
