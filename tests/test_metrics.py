"""指标计算单元测试。

覆盖 confidence/normalize_ratio/fback/rlatency/msg_count/active_days/
signal_level/base_score/neediness_penalty 等核心计算函数。
"""
import time
from datetime import datetime, timedelta

import pytest

from engine.config import Config, WeightsConfig
from engine.models.metrics import Metrics, MetricValue
from engine.analyzers.metrics import (
    _confidence,
    _normalize_ratio,
    _clamp,
    compute_fback,
    compute_rlatency,
    compute_msg_count,
    compute_active_days,
    compute_recent,
    compute_signal_level,
    compute_base_score,
    compute_neediness_penalty,
)


# ── 工具函数 ─────────────────────────────────────────────────────────────────

class TestHelpers:
    def test_confidence_zero(self):
        assert _confidence(0) == 0.0

    def test_confidence_small(self):
        """样本量 10 → confidence 在 0.1-0.5 之间。"""
        c = _confidence(10)
        assert 0.1 < c < 0.5

    def test_confidence_medium(self):
        """样本量 50 → confidence 在 0.5-0.8 之间。"""
        c = _confidence(50)
        assert 0.5 <= c < 0.8

    def test_confidence_large(self):
        """样本量 100 → confidence >= 0.8。"""
        assert _confidence(100) >= 0.8

    def test_confidence_very_large(self):
        """样本量 5000 → confidence 接近 1.0。"""
        c = _confidence(5000)
        assert c > 0.95

    def test_normalize_ratio_zero(self):
        assert _normalize_ratio(0) == 0.0

    def test_normalize_ratio_one(self):
        """1.0 / (1.0 + 1.0) = 0.5。"""
        assert abs(_normalize_ratio(1.0) - 0.5) < 1e-6

    def test_normalize_ratio_large(self):
        """大数 → 接近 1.0。"""
        assert _normalize_ratio(100) > 0.95

    def test_normalize_ratio_negative(self):
        assert _normalize_ratio(-1) == 0.0

    def test_clamp_basic(self):
        assert _clamp(0.5) == 0.5
        assert _clamp(-0.1) == 0.0
        assert _clamp(1.5) == 1.0
        assert _clamp(0.3, lo=0.2, hi=0.8) == 0.3
        assert _clamp(0.1, lo=0.2, hi=0.8) == 0.2


# ── Fback ────────────────────────────────────────────────────────────────────

class TestComputeFback:
    def test_balanced(self, tmp_db, insert_messages, now_ts):
        """双方字数相近 → raw ≈ 1.0，normalized ≈ 0.5。"""
        wxid = "wxid_client"
        my = "wxid_me"
        insert_messages(wxid, my, "你好啊今天怎么样", now_ts - 100)
        insert_messages(wxid, wxid, "挺好的你呢", now_ts - 50)
        insert_messages(wxid, my, "我也挺好的", now_ts - 10)
        result = compute_fback(tmp_db, my, wxid, window_days=30)
        assert result.raw > 0
        assert result.normalized > 0
        assert result.sample_size == 3

    def test_my_zero_chars(self, tmp_db, insert_messages, now_ts):
        """我方 0 字符 → raw=0, normalized=0。"""
        wxid = "wxid_client"
        my = "wxid_me"
        # 只有客户的消息
        insert_messages(wxid, wxid, "你好", now_ts - 100)
        insert_messages(wxid, wxid, "在吗", now_ts - 50)
        result = compute_fback(tmp_db, my, wxid, window_days=30)
        assert result.raw == 0.0
        assert result.normalized == 0.0

    def test_no_messages(self, tmp_db):
        """无消息 → raw=0, confidence=0。"""
        result = compute_fback(tmp_db, "wxid_me", "wxid_empty", window_days=30)
        assert result.raw == 0.0
        assert result.confidence == 0.0


# ── Rlatency ─────────────────────────────────────────────────────────────────

class TestComputeRlatency:
    def test_basic(self, tmp_db, insert_messages, now_ts):
        """交替消息 → 计算出回复速度比。"""
        wxid = "wxid_client"
        my = "wxid_me"
        base = now_ts - 3600
        # 交替消息，间隔 60 秒
        insert_messages(wxid, my, "你好", base)
        insert_messages(wxid, wxid, "嗯嗯", base + 60)
        insert_messages(wxid, my, "在干嘛", base + 120)
        insert_messages(wxid, wxid, "看书", base + 180)
        result = compute_rlatency(tmp_db, my, wxid, session_gap_hours=4)
        assert result.raw > 0
        assert result.sample_size > 0

    def test_too_few_messages(self, tmp_db, insert_messages, now_ts):
        """少于 2 条消息 → raw=0。"""
        wxid = "wxid_client"
        my = "wxid_me"
        insert_messages(wxid, my, "你好", now_ts - 100)
        result = compute_rlatency(tmp_db, my, wxid, session_gap_hours=4)
        assert result.raw == 0.0


# ── Msg Count ────────────────────────────────────────────────────────────────

class TestComputeMsgCount:
    def test_basic(self, tmp_db, insert_messages, now_ts):
        """插入 100 条消息 → 对数归一化。"""
        wxid = "wxid_client"
        my = "wxid_me"
        for i in range(100):
            insert_messages(wxid, my if i % 2 == 0 else wxid, f"msg_{i}", now_ts - i * 60)
        result = compute_msg_count(tmp_db, wxid)
        assert result.raw == 100
        assert 0.7 < result.normalized < 0.8  # log(101)/log(501) ≈ 0.74

    def test_zero_messages(self, tmp_db):
        """无消息 → raw=0, normalized=0。"""
        result = compute_msg_count(tmp_db, "wxid_empty")
        assert result.raw == 0
        assert result.normalized == 0.0

    def test_500_messages(self, tmp_db, insert_messages, now_ts):
        """500 条消息 → normalized 接近 1.0。"""
        wxid = "wxid_client"
        my = "wxid_me"
        for i in range(500):
            insert_messages(wxid, my, f"msg_{i}", now_ts - i * 60)
        result = compute_msg_count(tmp_db, wxid)
        assert result.raw == 500
        assert result.normalized >= 0.95


# ── Active Days ──────────────────────────────────────────────────────────────

class TestComputeActiveDays:
    def test_multiple_days(self, tmp_db, insert_messages, now_ts):
        """3 个不同日期 → active_days=3。"""
        wxid = "wxid_client"
        my = "wxid_me"
        today = now_ts
        yesterday = now_ts - 86400
        two_days_ago = now_ts - 172800
        insert_messages(wxid, my, "a", today)
        insert_messages(wxid, my, "b", yesterday)
        insert_messages(wxid, my, "c", two_days_ago)
        result = compute_active_days(tmp_db, wxid, window_days=30)
        assert result.raw >= 3

    def test_same_day(self, tmp_db, insert_messages, now_ts):
        """同一天多条消息 → active_days=1。"""
        wxid = "wxid_client"
        my = "wxid_me"
        for i in range(5):
            insert_messages(wxid, my, f"msg_{i}", now_ts - i * 60)
        result = compute_active_days(tmp_db, wxid, window_days=30)
        assert result.raw == 1


# ── Recent ───────────────────────────────────────────────────────────────────

class TestComputeRecent:
    def test_just_now(self, tmp_db, insert_messages, now_ts):
        """刚发的消息 → recent 约 0 天。"""
        wxid = "wxid_client"
        my = "wxid_me"
        insert_messages(wxid, my, "hi", now_ts)
        result = compute_recent(tmp_db, wxid, recency_decay=90)
        assert result.raw < 1.0
        assert result.normalized > 0.9

    def test_no_messages(self, tmp_db):
        """无消息 → raw=999, normalized=0。"""
        result = compute_recent(tmp_db, "wxid_empty", recency_decay=90)
        assert result.raw == 999
        assert result.normalized == 0.0


# ── Signal Level ─────────────────────────────────────────────────────────────

class TestSignalLevel:
    def test_strong(self):
        assert compute_signal_level(0.75) == "强意向"

    def test_medium(self):
        assert compute_signal_level(0.55) == "中意向"

    def test_weak(self):
        assert compute_signal_level(0.35) == "弱意向"

    def test_cold(self):
        assert compute_signal_level(0.20) == "冷淡"

    def test_none(self):
        assert compute_signal_level(0.10) == "无信号"

    def test_boundary_070(self):
        assert compute_signal_level(0.70) == "强意向"

    def test_boundary_050(self):
        assert compute_signal_level(0.50) == "中意向"

    def test_boundary_030(self):
        assert compute_signal_level(0.30) == "弱意向"

    def test_boundary_015(self):
        assert compute_signal_level(0.15) == "冷淡"


# ── Base Score ───────────────────────────────────────────────────────────────

class TestBaseScore:
    def test_all_zero(self):
        """全零指标 → base_score=0。"""
        m = Metrics()
        w = WeightsConfig({})
        assert compute_base_score(m, w) == 0.0

    def test_all_half(self):
        """全 0.5 指标 → base_score = 0.5 × (sum of weights - trend - qscore)。"""
        m = Metrics()
        half = MetricValue(raw=0.5, normalized=0.5, confidence=1.0, sample_size=100)
        for field_name in m.all_metrics():
            setattr(m, field_name, half)
        w = WeightsConfig({})
        score = compute_base_score(m, w)
        # 默认权重总和 = 1.0，但 trend(0.10) 不参与 base_score，qscore(0.00) 权重为 0
        # 所以 base_score = 0.5 * (1.0 - 0.10) = 0.45
        assert abs(score - 0.45) < 0.01

    def test_top_target_bonus(self):
        """top_target=True → +0.10。"""
        m = Metrics()
        half = MetricValue(raw=0.5, normalized=0.5, confidence=1.0, sample_size=100)
        for field_name in m.all_metrics():
            setattr(m, field_name, half)
        w = WeightsConfig({})
        normal = compute_base_score(m, w)
        boosted = compute_base_score(m, w, top_target=True)
        assert abs(boosted - normal - 0.10) < 0.01

    def test_trend_excluded(self):
        """trend 不参与 base_score 计算。"""
        m = Metrics()
        zero = MetricValue(raw=0.0, normalized=0.0, confidence=1.0, sample_size=100)
        high_trend = MetricValue(raw=1.0, normalized=1.0, confidence=1.0, sample_size=100)
        for field_name in m.all_metrics():
            setattr(m, field_name, zero)
        m.trend = high_trend
        w = WeightsConfig({})
        assert compute_base_score(m, w) == 0.0


# ── Neediness Penalty ────────────────────────────────────────────────────────

class TestNeedinessPenalty:
    def test_balanced_no_penalty(self, tmp_db, insert_messages, now_ts):
        """消息量比 <= 2 → 无惩罚。"""
        wxid = "wxid_client"
        my = "wxid_me"
        base = now_ts - 3600
        # 客户 10 条，我 10 条，交替发送
        for i in range(10):
            insert_messages(wxid, my if i % 2 == 0 else wxid, f"msg_{i}", base + i * 60)
        result = compute_neediness_penalty(tmp_db, my, wxid, session_gap_hours=4)
        assert result >= 0.9  # 基本无惩罚

    def test_excessive_messaging_penalty(self, tmp_db, insert_messages, now_ts):
        """我发远多于客户 → 触发惩罚。"""
        wxid = "wxid_client"
        my = "wxid_me"
        base = now_ts - 7200
        # 我发 30 条，客户发 5 条
        for i in range(30):
            insert_messages(wxid, my, f"msg_{i}", base + i * 60)
        for i in range(5):
            insert_messages(wxid, wxid, f"reply_{i}", base + 3600 + i * 60)
        result = compute_neediness_penalty(tmp_db, my, wxid, session_gap_hours=4)
        assert result < 1.0  # 有惩罚

    def test_too_few_messages(self, tmp_db, insert_messages, now_ts):
        """少于 2 条消息 → 返回 1.0。"""
        wxid = "wxid_client"
        my = "wxid_me"
        insert_messages(wxid, my, "hi", now_ts)
        result = compute_neediness_penalty(tmp_db, my, wxid, session_gap_hours=4)
        assert result == 1.0

    def test_no_client_messages(self, tmp_db, insert_messages, now_ts):
        """客户没发消息 → 返回 0.5。"""
        wxid = "wxid_client"
        my = "wxid_me"
        base = now_ts - 3600
        for i in range(5):
            insert_messages(wxid, my, f"msg_{i}", base + i * 60)
        result = compute_neediness_penalty(tmp_db, my, wxid, session_gap_hours=4)
        assert result == 0.5
