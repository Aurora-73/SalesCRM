"""信号关键词检测测试。"""
import pytest
from datetime import datetime


def _ts(day_offset=0):
    return int(datetime(2026, 6, 1, 12, 0).timestamp()) + day_offset * 86400


class TestDetectSignals:
    def test_rejection(self):
        from engine.agent.signals import _detect_signals
        msgs = [{"sender": "客户", "content": "对不起我不喜欢你", "timestamp": _ts()}]
        r = _detect_signals(msgs)
        assert "rejection" in r
        assert len(r["rejection"]) == 1

    def test_confession(self):
        from engine.agent.signals import _detect_signals
        msgs = [{"sender": "客户", "content": "我们签约吧", "timestamp": _ts()}]
        r = _detect_signals(msgs)
        assert "confession" in r

    def test_invitation_only_me(self):
        from engine.agent.signals import _detect_signals
        msgs = [{"sender": "我", "content": "出来玩吗", "timestamp": _ts()}]
        r = _detect_signals(msgs)
        assert "invitation" not in r  # 我发出的不算会面信号

    def test_invitation_from_client(self):
        from engine.agent.signals import _detect_signals
        msgs = [{"sender": "客户", "content": "周末一起出来吧", "timestamp": _ts()}]
        r = _detect_signals(msgs)
        assert "invitation" in r

    def test_no_signal(self):
        from engine.agent.signals import _detect_signals
        msgs = [{"sender": "客户", "content": "今天天气真好", "timestamp": _ts()}]
        r = _detect_signals(msgs)
        assert len(r) == 0

    def test_empty_messages(self):
        from engine.agent.signals import _detect_signals
        r = _detect_signals([])
        assert len(r) == 0


class TestDetectManipulation:
    def test_money_request(self):
        from engine.agent.signals import detect_manipulation_signals
        msgs = [{"sender_id": "client", "content": "借我点钱", "timestamp": _ts()}]
        r = detect_manipulation_signals(msgs, "my_wxid")
        assert "money_requests" in r

    def test_sweet_escalation(self):
        from engine.agent.signals import detect_manipulation_signals
        msgs = [{"sender_id": "client", "content": "你是全世界最好的合作伙伴", "timestamp": _ts()}]
        r = detect_manipulation_signals(msgs, "my_wxid")
        assert "sweet_escalation" in r

    def test_victim_play(self):
        from engine.agent.signals import detect_manipulation_signals
        msgs = [{"sender_id": "client", "content": "我好害怕没有人对我好", "timestamp": _ts()}]
        r = detect_manipulation_signals(msgs, "my_wxid")
        assert "victim_play" in r

    def test_no_signal_normal_chat(self):
        from engine.agent.signals import detect_manipulation_signals
        msgs = [{"sender_id": "client", "content": "在干嘛", "timestamp": _ts()}]
        r = detect_manipulation_signals(msgs, "my_wxid")
        assert len(r) == 0

    def test_my_messages_ignored(self):
        from engine.agent.signals import detect_manipulation_signals
        msgs = [{"sender_id": "my_wxid", "content": "借我点钱", "timestamp": _ts()}]
        r = detect_manipulation_signals(msgs, "my_wxid")
        assert "money_requests" not in r
