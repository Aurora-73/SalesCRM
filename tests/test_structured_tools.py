"""Batch 1 结构化工具测试 — chat_data / brief_data / message_context_data / save_analysis。"""
import sqlite3
import time
from pathlib import Path

import pytest
import yaml

from engine.agent.response import ok, err, ToolEnvelope
from engine.agent.chat import _query_chat_messages, agent_chat_data, agent_chat
from engine.agent.brief import agent_brief_data, agent_brief
from engine.agent.context import query_message_context
from engine.agent.write import agent_save_analysis

NOW = int(time.time())
HOUR = 3600
DAY = 86400


def _make_person(conn, name="测试客户", wxid="wxid_target"):
    """创建测试用 person 并 resolve。仅写入 contacts + conversations，
    由 resolve_contact → bootstrap_identity 自动创建 people + contact_accounts。
    使用 INSERT OR REPLACE 保证幂等。"""
    from engine.identity import resolve_contact
    conn.execute(
        "INSERT OR REPLACE INTO contacts (id, nickname, display_name, type, updated_at) VALUES (?, ?, ?, 'friend', ?)",
        (wxid, name, name, NOW),
    )
    conn.execute(
        "INSERT OR REPLACE INTO conversations (id, type, display_name, contact_id, updated_at) VALUES (?, 'private', ?, ?, ?)",
        (wxid, name, wxid, NOW),
    )
    conn.commit()
    result = resolve_contact(conn, name)
    assert result.person is not None, f"Failed to resolve person: {name}"
    return result.person


def _insert_msg(conn, conversation_id, sender_id, content, timestamp, msg_type=1, platform="wechat", source="sync"):
    """插入单条消息并返回 id。"""
    import hashlib
    raw = f"{conversation_id}|{sender_id}|{content}|{timestamp}|{msg_type}"
    msg_id = hashlib.md5(raw.encode()).hexdigest()
    conn.execute(
        """INSERT OR IGNORE INTO messages
           (id, conversation_id, sender_id, timestamp, type, content, platform, source, synced_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (msg_id, conversation_id, sender_id, timestamp, msg_type, content, platform, source, timestamp),
    )
    conn.commit()
    return msg_id


# ═══════════════════════════════════════════════════════════════════
# response.py
# ═══════════════════════════════════════════════════════════════════

class TestResponse:
    def test_ok_basic(self):
        result = ok({"key": "value"}, count=5)
        assert result == {"status": "ok", "data": {"key": "value"}, "meta": {"count": 5}}

    def test_err_basic(self):
        result = err("NOT_FOUND", "未找到", trace_id="abc")
        assert result["status"] == "error"
        assert result["error"] == {"code": "NOT_FOUND", "message": "未找到"}
        assert result["meta"] == {"trace_id": "abc"}

    def test_tool_envelope_type(self):
        e = ToolEnvelope(status="ok", data=[1, 2], meta={"took": 12})
        assert e.status == "ok"
        assert e.data == [1, 2]
        assert e.meta == {"took": 12}


# ═══════════════════════════════════════════════════════════════════
# _query_chat_messages (shared SQL layer)
# ═══════════════════════════════════════════════════════════════════

class TestQueryChatMessages:
    def test_basic_fields(self, tmp_db, test_config):
        person = _make_person(tmp_db)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "客户消息1", NOW - 2 * HOUR)
        _insert_msg(tmp_db, "wxid_target", "wxid_testuser", "我的消息1", NOW - HOUR)

        result = _query_chat_messages(tmp_db, test_config, person, recent=50)
        assert result["total"] == 2
        assert result["returned"] == 2

        msg = result["messages"][0]
        assert set(msg.keys()) == {
            "id", "conversation_id", "sender_id", "is_mine",
            "timestamp", "content", "type", "platform", "source",
        }
        assert msg["conversation_id"] == "wxid_target"

    def test_is_mine_labeling(self, tmp_db, test_config):
        person = _make_person(tmp_db)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "客户的消息", NOW)
        _insert_msg(tmp_db, "wxid_target", "wxid_testuser", "我的消息", NOW + 1)

        result = _query_chat_messages(tmp_db, test_config, person, recent=50)
        msgs = result["messages"]
        assert msgs[0]["is_mine"] is False
        assert msgs[1]["is_mine"] is True

    def test_recent_limit(self, tmp_db, test_config):
        person = _make_person(tmp_db)
        for i in range(10):
            _insert_msg(tmp_db, "wxid_target", "wxid_target", f"msg{i}", NOW + i * 60)

        result = _query_chat_messages(tmp_db, test_config, person, recent=3)
        assert result["total"] == 10
        assert result["returned"] == 3
        # 应该是最新的 3 条
        contents = [m["content"] for m in result["messages"]]
        assert contents == ["msg7", "msg8", "msg9"]

    def test_keyword_filter(self, tmp_db, test_config):
        person = _make_person(tmp_db)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "今天天气真好", NOW)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "明天见", NOW + 60)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "天气不错", NOW + 120)

        result = _query_chat_messages(tmp_db, test_config, person, recent=50, keyword="天气")
        assert result["returned"] == 2
        contents = [m["content"] for m in result["messages"]]
        assert "今天天气真好" in contents
        assert "天气不错" in contents

    def test_keyword_context_lines(self, tmp_db, test_config):
        person = _make_person(tmp_db)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "A", NOW)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "B keyword", NOW + 60)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "C", NOW + 120)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "D", NOW + 180)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "E keyword2", NOW + 240)

        result = _query_chat_messages(tmp_db, test_config, person, recent=50,
                                      keyword="keyword", context_lines=1)
        # B keyword → gets A, B, C (1 before, 1 after)
        # E keyword2 → gets D, E (1 before, 0 after)
        assert result["returned"] == 5

    def test_date_filter(self, tmp_db, test_config):
        person = _make_person(tmp_db)
        from datetime import datetime
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "old", NOW - 10 * DAY)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "recent", NOW - DAY)

        recent_date = datetime.fromtimestamp(NOW - 2 * DAY).strftime("%Y-%m-%d")
        result = _query_chat_messages(tmp_db, test_config, person, recent=50,
                                      from_date=recent_date)
        assert result["returned"] == 1
        assert result["messages"][0]["content"] == "recent"

    def test_no_cross_conversation(self, tmp_db, test_config):
        person = _make_person(tmp_db)
        # 属于目标会话
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "target_msg", NOW)
        # 属于另一个会话（即使该人的另一个 account）
        _insert_msg(tmp_db, "wxid_other", "wxid_target", "other_msg", NOW + 60)

        result = _query_chat_messages(tmp_db, test_config, person, recent=50)
        # 只有 target 会话的消息（因为 account 只关联了 wxid_target）
        assert result["total"] == 1
        assert result["messages"][0]["content"] == "target_msg"


# ═══════════════════════════════════════════════════════════════════
# agent_chat_data (structured wrapper)
# ═══════════════════════════════════════════════════════════════════

class TestAgentChatData:
    def test_returns_tool_envelope_format(self, tmp_db, test_config):
        person = _make_person(tmp_db)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "hello", NOW)

        result = agent_chat_data(tmp_db, test_config, person, recent=5)
        assert result["status"] == "ok"
        assert "data" in result
        assert "meta" in result
        assert result["meta"]["person_id"]  # bootstrap 生成的 ID

    def test_includes_filter_info(self, tmp_db, test_config):
        person = _make_person(tmp_db)
        result = agent_chat_data(tmp_db, test_config, person, recent=5,
                                 keyword="hello", from_date="2025-01-01")
        assert result["data"]["filter"] == {
            "keyword": "hello",
            "from_date": "2025-01-01",
            "to_date": None,
            "context_lines": 0,
        }

    def test_total_and_returned(self, tmp_db, test_config):
        person = _make_person(tmp_db)
        for i in range(20):
            _insert_msg(tmp_db, "wxid_target", "wxid_target", f"msg{i}", NOW + i * 60)

        result = agent_chat_data(tmp_db, test_config, person, recent=5)
        assert result["data"]["total"] == 20
        assert result["data"]["returned"] == 5


# ═══════════════════════════════════════════════════════════════════
# agent_chat (Markdown, backward compat)
# ═══════════════════════════════════════════════════════════════════

class TestAgentChatBackwardCompat:
    def test_returns_markdown_string(self, tmp_db, test_config):
        person = _make_person(tmp_db)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "hello world", NOW)

        result = agent_chat(tmp_db, test_config, person, recent=5)
        assert isinstance(result, str)
        assert result.startswith("# Chat Evidence:")
        assert "hello world" in result
        assert person.display_name in result

    def test_shares_sql_with_chat_data(self, tmp_db, test_config):
        """chat_data 和 chat 返回的消息数一致。"""
        person = _make_person(tmp_db)
        for i in range(5):
            _insert_msg(tmp_db, "wxid_target", "wxid_target", f"msg{i}", NOW + i * 60)

        data_result = agent_chat_data(tmp_db, test_config, person, recent=10)
        markdown = agent_chat(tmp_db, test_config, person, recent=10)

        assert data_result["data"]["returned"] == 5
        # Markdown 里也包含所有 5 条消息的内容
        for i in range(5):
            assert f"msg{i}" in markdown


# ═══════════════════════════════════════════════════════════════════
# query_message_context
# ═══════════════════════════════════════════════════════════════════

class TestQueryMessageContext:
    def test_before_and_after(self, tmp_db, test_config):
        _make_person(tmp_db)
        target_id = _insert_msg(tmp_db, "wxid_target", "wxid_target", "target", NOW)
        b1 = _insert_msg(tmp_db, "wxid_target", "wxid_target", "before1", NOW - 120)
        b2 = _insert_msg(tmp_db, "wxid_target", "wxid_target", "before2", NOW - 60)
        a1 = _insert_msg(tmp_db, "wxid_target", "wxid_target", "after1", NOW + 60)
        a2 = _insert_msg(tmp_db, "wxid_target", "wxid_target", "after2", NOW + 120)

        result = query_message_context(tmp_db, [target_id], before=3, after=3,
                                       my_wxid=test_config.my_wxid)
        assert result["status"] == "ok"
        ctx = result["data"]["contexts"][0]

        assert ctx["target"]["id"] == target_id
        assert ctx["target"]["content"] == "target"
        assert len(ctx["before"]) == 2
        assert len(ctx["after"]) == 2
        # before/after 均为时间正序（用于按序阅读）
        assert ctx["before"][0]["content"] == "before1"  # 最早
        assert ctx["before"][1]["content"] == "before2"  # 更近
        assert ctx["after"][0]["content"] == "after1"
        assert ctx["after"][1]["content"] == "after2"

    def test_no_cross_conversation(self, tmp_db, test_config):
        _make_person(tmp_db)
        target_id = _insert_msg(tmp_db, "wxid_target", "wxid_target", "target", NOW)
        # 另一个会话的消息（时间在 target 前后）
        _insert_msg(tmp_db, "wxid_other", "wxid_other", "other_before", NOW - 60)
        _insert_msg(tmp_db, "wxid_other", "wxid_other", "other_after", NOW + 60)
        # target 会话的上下文
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "real_before", NOW - 120)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "real_after", NOW + 120)

        result = query_message_context(tmp_db, [target_id], before=5, after=5,
                                       my_wxid=test_config.my_wxid)
        ctx = result["data"]["contexts"][0]

        before_contents = [m["content"] for m in ctx["before"]]
        after_contents = [m["content"] for m in ctx["after"]]
        assert "other_before" not in before_contents
        assert "other_after" not in after_contents
        assert "real_before" in before_contents
        assert "real_after" in after_contents

    def test_target_has_is_mine(self, tmp_db, test_config):
        _make_person(tmp_db)
        target_id = _insert_msg(tmp_db, "wxid_target", "wxid_target", "客户的消息", NOW)

        result = query_message_context(tmp_db, [target_id], before=1, after=1,
                                       my_wxid=test_config.my_wxid)
        ctx = result["data"]["contexts"][0]
        assert ctx["target"]["is_mine"] is False

        # before/after 也有 is_mine
        if ctx["before"]:
            assert "is_mine" in ctx["before"][0]
        if ctx["after"]:
            assert "is_mine" in ctx["after"][0]

    def test_missing_message_id(self, tmp_db, test_config):
        """不存在的 message ID 被静默跳过。"""
        _make_person(tmp_db)
        result = query_message_context(tmp_db, ["nonexistent_id"], before=3, after=3,
                                       my_wxid=test_config.my_wxid)
        assert result["status"] == "ok"
        assert result["data"]["contexts"] == []

    def test_multiple_message_ids(self, tmp_db, test_config):
        _make_person(tmp_db)
        id1 = _insert_msg(tmp_db, "wxid_target", "wxid_target", "first", NOW - 60)
        id2 = _insert_msg(tmp_db, "wxid_target", "wxid_target", "second", NOW)

        result = query_message_context(tmp_db, [id1, id2], before=1, after=1,
                                       my_wxid=test_config.my_wxid)
        assert len(result["data"]["contexts"]) == 2
        assert result["data"]["contexts"][0]["target"]["id"] == id1
        assert result["data"]["contexts"][1]["target"]["id"] == id2

    def test_respects_before_after_limits(self, tmp_db, test_config):
        _make_person(tmp_db)
        target_id = _insert_msg(tmp_db, "wxid_target", "wxid_target", "target", NOW)
        for i in range(10):
            _insert_msg(tmp_db, "wxid_target", "wxid_target", f"before{i}", NOW - (i + 1) * 60)
            _insert_msg(tmp_db, "wxid_target", "wxid_target", f"after{i}", NOW + (i + 1) * 60)

        result = query_message_context(tmp_db, [target_id], before=3, after=2,
                                       my_wxid=test_config.my_wxid)
        ctx = result["data"]["contexts"][0]
        assert len(ctx["before"]) == 3
        assert len(ctx["after"]) == 2


# ═══════════════════════════════════════════════════════════════════
# agent_brief_data (structured brief)
# ═══════════════════════════════════════════════════════════════════

class TestAgentBriefData:
    def test_returns_tool_envelope_format(self, tmp_db, test_config):
        _make_person(tmp_db)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "hello", NOW)
        _insert_msg(tmp_db, "wxid_target", "wxid_testuser", "hi", NOW + 60)

        result = agent_brief_data(tmp_db, test_config, _make_person(tmp_db))
        assert result["status"] == "ok"
        assert "meta" in result
        assert result["meta"]["person_id"]  # bootstrap 生成的 ID

    def test_required_top_level_keys(self, tmp_db, test_config):
        _make_person(tmp_db)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "hello", NOW)

        result = agent_brief_data(tmp_db, test_config, _make_person(tmp_db))
        data = result["data"]
        required = ["identity", "message_stats", "metrics", "events",
                    "signals", "recent_messages", "latest_analysis", "recommendations"]
        for key in required:
            assert key in data, f"Missing required key: {key}"

    def test_identity_fields(self, tmp_db, test_config):
        _make_person(tmp_db)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "hello", NOW)

        result = agent_brief_data(tmp_db, test_config, _make_person(tmp_db))
        identity = result["data"]["identity"]
        assert identity["person_id"]  # bootstrap 生成的 ID
        assert identity["display_name"] == "测试客户"
        assert len(identity["accounts"]) >= 1
        assert identity["accounts"][0]["wxid"] == "wxid_target"

    def test_message_stats(self, tmp_db, test_config):
        _make_person(tmp_db)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "客户的消息", NOW)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "客户的消息2", NOW + 60)
        _insert_msg(tmp_db, "wxid_target", "wxid_testuser", "我的消息", NOW + 120)

        # 重新 resolve 以确保 account 已绑定
        person = _make_person(tmp_db)
        result = agent_brief_data(tmp_db, test_config, person)
        stats = result["data"]["message_stats"]
        assert stats["total"] == 3
        assert stats["my_count"] == 1
        assert stats["customer_count"] == 2

    def test_recent_messages_include_id(self, tmp_db, test_config):
        _make_person(tmp_db)
        msg_id = _insert_msg(tmp_db, "wxid_target", "wxid_target", "hello", NOW)

        person = _make_person(tmp_db)
        result = agent_brief_data(tmp_db, test_config, person)
        recent = result["data"]["recent_messages"]
        assert len(recent) >= 1
        assert "id" in recent[0]
        assert "sender_id" in recent[0]
        assert "is_mine" in recent[0]

    def test_recommendations_structure(self, tmp_db, test_config):
        _make_person(tmp_db)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "hello", NOW)

        person = _make_person(tmp_db)
        result = agent_brief_data(tmp_db, test_config, person)
        recs = result["data"]["recommendations"]
        assert "wiki" in recs
        assert "frameworks" in recs
        assert isinstance(recs["wiki"], list)
        assert isinstance(recs["frameworks"], list)


# ═══════════════════════════════════════════════════════════════════
# agent_brief (Markdown, backward compat)
# ═══════════════════════════════════════════════════════════════════

class TestAgentBriefBackwardCompat:
    def test_returns_markdown_string(self, tmp_db, test_config):
        _make_person(tmp_db)
        _insert_msg(tmp_db, "wxid_target", "wxid_target", "hello", NOW)

        person = _make_person(tmp_db)
        result = agent_brief(tmp_db, test_config, person, compact=True)
        assert isinstance(result, str)
        assert result.startswith("# Brief:")
        assert "测试客户" in result


# ═══════════════════════════════════════════════════════════════════
# agent_save_analysis (new optional fields)
# ═══════════════════════════════════════════════════════════════════

class TestSaveAnalysisNewFields:
    def test_evidence_refs_written(self, tmp_db, test_config, tmp_path):
        person = _make_person(tmp_db)
        # patch OUTPUTS_ANALYSIS_DIR to use tmp_path
        import engine.agent.write as write_mod
        import engine.config as config_mod
        orig_dir = config_mod.OUTPUTS_ANALYSIS_DIR
        config_mod.OUTPUTS_ANALYSIS_DIR = tmp_path / "analysis"

        try:
            evidence = [
                {"message_id": "msg_001", "quote": "对产品感兴趣", "note": "需求信号"},
                {"message_id": "msg_002", "quote": "预算多少", "note": "购买意向"},
            ]
            path = agent_save_analysis(
                person, stage="需求确认期", confidence=0.75, reasoning="测试依据",
                diagnosis="测试诊断", strategy="测试策略",
                evidence_refs=evidence,
                metric_snapshot={"composite": 0.65, "fback": 0.4},
                data_window={"from_date": "2025-01-01", "to_date": "2025-06-01"},
            )
            assert path.is_file()

            with open(path, encoding="utf-8") as f:
                saved = yaml.safe_load(f)
            assert saved["evidence_refs"] == evidence
            assert saved["metric_snapshot"] == {"composite": 0.65, "fback": 0.4}
            assert saved["data_window"] == {"from_date": "2025-01-01", "to_date": "2025-06-01"}
        finally:
            config_mod.OUTPUTS_ANALYSIS_DIR = orig_dir

    def test_new_fields_optional(self, tmp_db, test_config, tmp_path):
        """不传新字段时，save_analysis 行为不变。"""
        person = _make_person(tmp_db)
        import engine.agent.write as write_mod
        import engine.config as config_mod
        orig_dir = config_mod.OUTPUTS_ANALYSIS_DIR
        config_mod.OUTPUTS_ANALYSIS_DIR = tmp_path / "analysis2"

        try:
            path = agent_save_analysis(
                person, stage="初步接触期", confidence=0.5, reasoning="无",
                diagnosis="诊断", strategy="策略",
            )
            assert path.is_file()

            with open(path, encoding="utf-8") as f:
                saved = yaml.safe_load(f)
            # 新字段不应出现
            assert "evidence_refs" not in saved
            assert "metric_snapshot" not in saved
            assert "data_window" not in saved
            # 老字段正常
            assert saved["stage"]["stage"] == "初步接触期"
            assert saved["diagnosis"] == "诊断"
        finally:
            config_mod.OUTPUTS_ANALYSIS_DIR = orig_dir

    def test_changed_from_previous(self, tmp_db, test_config, tmp_path):
        person = _make_person(tmp_db)
        import engine.agent.write as write_mod
        import engine.config as config_mod
        orig_dir = config_mod.OUTPUTS_ANALYSIS_DIR
        config_mod.OUTPUTS_ANALYSIS_DIR = tmp_path / "analysis3"

        try:
            path = agent_save_analysis(
                person, stage="需求确认期", confidence=0.8, reasoning="...",
                diagnosis="...", strategy="...",
                changed_from_previous="阶段从初步接触期→需求确认期，fback 从 0.2→0.5",
            )
            with open(path, encoding="utf-8") as f:
                saved = yaml.safe_load(f)
            assert saved["changed_from_previous"] == "阶段从初步接触期→需求确认期，fback 从 0.2→0.5"
        finally:
            config_mod.OUTPUTS_ANALYSIS_DIR = orig_dir

    def test_latest_and_history_created(self, tmp_db, test_config, tmp_path):
        """latest.yaml 和 history/*.yaml 都被创建。"""
        person = _make_person(tmp_db)
        import engine.agent.write as write_mod
        import engine.config as config_mod
        orig_dir = config_mod.OUTPUTS_ANALYSIS_DIR
        config_mod.OUTPUTS_ANALYSIS_DIR = tmp_path / "analysis4"

        try:
            path = agent_save_analysis(
                person, stage="需求确认期", confidence=0.6, reasoning="...",
                diagnosis="...", strategy="...",
                evidence_refs=[{"message_id": "x", "quote": "y"}],
            )
            # latest.yaml
            assert path.is_file()
            assert path.name == "latest.yaml"
            # history
            history_dir = path.parent / "history"
            assert history_dir.is_dir()
            history_files = list(history_dir.glob("*.yaml"))
            assert len(history_files) == 1
        finally:
            config_mod.OUTPUTS_ANALYSIS_DIR = orig_dir


# ═══════════════════════════════════════════════════════════════════
# agent_chat_data → message_context_data 联动
# ═══════════════════════════════════════════════════════════════════

class TestStructuredToolsIntegration:
    """chat_data 返回的 message id 可以直接传给 message_context_data。"""

    def test_chat_data_to_context_roundtrip(self, tmp_db, test_config):
        _make_person(tmp_db)
        target_id = _insert_msg(tmp_db, "wxid_target", "wxid_target", "关键消息", NOW)
        for i in range(3):
            _insert_msg(tmp_db, "wxid_target", "wxid_target", f"before{i}", NOW - (i + 1) * 60)
            _insert_msg(tmp_db, "wxid_target", "wxid_target", f"after{i}", NOW + (i + 1) * 60)

        person = _make_person(tmp_db)
        chat_result = agent_chat_data(tmp_db, test_config, person, recent=10)
        msgs = chat_result["data"]["messages"]
        # 找到关键消息
        key_msg = [m for m in msgs if m["content"] == "关键消息"]
        assert len(key_msg) == 1

        ctx_result = query_message_context(tmp_db, [key_msg[0]["id"]],
                                           before=2, after=2,
                                           my_wxid=test_config.my_wxid)
        ctx = ctx_result["data"]["contexts"][0]
        assert ctx["target"]["content"] == "关键消息"
        assert len(ctx["before"]) == 2
        assert len(ctx["after"]) == 2
