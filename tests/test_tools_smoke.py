"""tools.py 导入冒烟测试。"""
import pytest


class TestImports:
    """所有 tools.py 导出函数可正常导入。"""

    def test_read_tools(self):
        from engine.tools import brief, chat, evidence, metrics, rank, status
        from engine.tools import wiki_search, wiki_show, moments_stats
        assert callable(brief)
        assert callable(chat)
        assert callable(evidence)
        assert callable(metrics)
        assert callable(rank)
        assert callable(status)
        assert callable(wiki_search)
        assert callable(wiki_show)
        assert callable(moments_stats)

    def test_write_tools(self):
        from engine.tools import note, date, evaluate, events
        from engine.tools import save_analysis, save_from_markdown
        assert callable(note)
        assert callable(date)
        assert callable(evaluate)
        assert callable(events)
        assert callable(save_analysis)
        assert callable(save_from_markdown)

    def test_identity_tools(self):
        from engine.tools import contact, exclude, failure, sticker
        assert callable(contact)
        assert callable(exclude)
        assert callable(failure)
        assert callable(sticker)

    def test_sync_tools(self):
        from engine.tools import sync, sync_person, sync_moments, weekly
        assert callable(sync)
        assert callable(sync_person)
        assert callable(sync_moments)
        assert callable(weekly)

    def test_formula_tools(self):
        from engine.tools import (
            formula_params, formula_ivi, formula_spe, formula_ews,
            formula_is, formula_gap_effect, formula_eev, formula_cs, formula_action,
        )
        assert callable(formula_params)
        assert callable(formula_ivi)
        assert callable(formula_spe)
        assert callable(formula_ews)
        assert callable(formula_is)
        assert callable(formula_gap_effect)
        assert callable(formula_eev)
        assert callable(formula_cs)
        assert callable(formula_action)

    def test_module_consistency(self):
        """brief/chat/moments_stats 等从 tools 导入的函数，底层模块也导出相同对象。"""
        from engine.tools import brief as tools_brief
        from engine.agent.brief import agent_brief as mod_brief
        # tools.py 里的 brief 是包装函数，不是同一个对象，但都可调用
        assert callable(tools_brief)
        assert callable(mod_brief)

        from engine.tools import moments_stats as tools_moments
        from engine.agent.moments import moments_stats as mod_moments
        assert tools_moments is mod_moments

    def test_structured_tools_import(self):
        from engine.tools import chat_data, brief_data, message_context_data
        assert callable(chat_data)
        assert callable(brief_data)
        assert callable(message_context_data)

    def test_formula_params_signature(self):
        import inspect
        from engine.tools import formula_params
        sig = inspect.signature(formula_params)
        params = list(sig.parameters.keys())
        assert "name" in params
        assert "conn" in params


class TestStructuredTools:
    """chat_data / brief_data / message_context_data 功能测试。"""

    def test_chat_data_returns_structured_format(self, tmp_db, test_config, insert_messages, setup_contacts, now_ts):
        wxid = "wxid_target"
        setup_contacts(wxid, "目标用户", display_name="目标用户")
        # Insert messages from both sides (my_wxid = wxid_testuser from test_config)
        insert_messages(wxid, wxid, "你好", now_ts - 3600)
        insert_messages(wxid, "wxid_testuser", "你好呀", now_ts - 1800)
        insert_messages(wxid, wxid, "在干嘛", now_ts)

        from engine.agent.chat import agent_chat_data
        from engine.identity import resolve_contact
        result = resolve_contact(tmp_db, "目标用户")
        assert result.person is not None
        r = agent_chat_data(tmp_db, test_config, result.person, recent=10)

        assert r["status"] == "ok"
        assert "meta" in r
        assert r["meta"]["display_name"] == "目标用户"
        data = r["data"]
        assert len(data["messages"]) == 3
        m = data["messages"][0]
        for field in ["id", "conversation_id", "sender_id", "is_mine", "timestamp", "content", "type", "platform", "source"]:
            assert field in m, f"missing field: {field}"
        # Check is_mine labeling
        my_msgs = [m for m in data["messages"] if m["is_mine"]]
        target_msgs = [m for m in data["messages"] if not m["is_mine"]]
        assert len(my_msgs) == 1
        assert len(target_msgs) == 2

    def test_message_context_data_no_cross_conversation(self, tmp_db, test_config, insert_messages, now_ts):
        """message_context_data 不会跨会话串数据。"""
        conv_a = "wxid_conv_a"
        conv_b = "wxid_conv_b"
        # Conversation A messages
        insert_messages(conv_a, "wxid_other", "A-msg-1", now_ts - 300)
        target_ts = now_ts
        target_id = insert_messages(conv_a, "wxid_other", "A-target", target_ts)
        insert_messages(conv_a, "wxid_other", "A-msg-2", now_ts + 300)
        # Conversation B messages (should NOT appear in context)
        insert_messages(conv_b, "wxid_other", "B-noise", now_ts - 60)
        insert_messages(conv_b, "wxid_other", "B-noise-2", now_ts + 60)

        from engine.agent.context import query_message_context
        r = query_message_context(tmp_db, [target_id], before=5, after=5, my_wxid="wxid_testuser")

        assert r["status"] == "ok"
        ctx = r["data"]["contexts"][0]
        # target 应有 is_mine
        assert "is_mine" in ctx["target"]
        # before 和 after 的消息应全部来自 conv_a
        all_msg_ids = {ctx["target"]["id"]}
        for m in ctx["before"] + ctx["after"]:
            all_msg_ids.add(m["id"])
            assert "is_mine" in m
        # 不应包含 conv_b 的消息
        b_ids = {row["id"] for row in tmp_db.execute(
            "SELECT id FROM messages WHERE conversation_id = ?", (conv_b,)
        ).fetchall()}
        assert all_msg_ids.isdisjoint(b_ids), "context should not include messages from other conversation"
        # before 应在 target 之前，after 应在之后
        for m in ctx["before"]:
            assert m["timestamp"] < target_ts
        for m in ctx["after"]:
            assert m["timestamp"] > target_ts

    def test_brief_data_returns_required_keys(self, tmp_db, test_config, insert_messages, setup_contacts, now_ts):
        wxid = "wxid_brief_test"
        setup_contacts(wxid, "简要测试", display_name="简要测试")
        insert_messages(wxid, wxid, "消息1", now_ts - 7200)
        insert_messages(wxid, "wxid_testuser", "消息2", now_ts - 3600)

        from engine.agent.brief import agent_brief_data
        from engine.identity import resolve_contact
        result = resolve_contact(tmp_db, "简要测试")
        assert result.person is not None
        r = agent_brief_data(tmp_db, test_config, result.person)

        assert r["status"] == "ok"
        data = r["data"]
        required = ["identity", "message_stats", "metrics", "events", "signals",
                    "recent_messages", "latest_analysis", "recommendations"]
        for key in required:
            assert key in data, f"missing required key: {key}"
        assert data["identity"]["display_name"] == "简要测试"
        assert data["message_stats"]["total"] == 2
        assert len(data["recent_messages"]) == 2

    def test_response_helpers(self):
        from engine.agent.response import ok, err, ToolEnvelope
        r = ok({"key": "value"}, tool="test")
        assert r == {"status": "ok", "data": {"key": "value"}, "meta": {"tool": "test"}}
        r = err("NOT_FOUND", "找不到")
        assert r == {"status": "error", "error": {"code": "NOT_FOUND", "message": "找不到"}, "meta": {}}
        # ToolEnvelope 是类型标注用的 dataclass
        env = ToolEnvelope(status="ok", data=[1, 2], meta={})
        assert env.status == "ok"

    def test_save_analysis_new_fields(self, tmp_db, test_config, setup_contacts, now_ts, tmp_path):
        wxid = "wxid_save_test"
        setup_contacts(wxid, "保存测试", display_name="保存测试")

        from engine.agent.write import agent_save_analysis
        from engine.identity import resolve_contact
        result = resolve_contact(tmp_db, "保存测试")
        assert result.person is not None

        # 临时覆盖 OUTPUTS_ANALYSIS_DIR — agent_save_analysis 内部 from engine.config import ...
        from unittest.mock import patch
        analysis_dir = tmp_path / "analysis"
        analysis_dir.mkdir()
        with patch("engine.config.OUTPUTS_ANALYSIS_DIR", analysis_dir):
            path = agent_save_analysis(
                result.person,
                stage="冷淡期", confidence=0.75, reasoning="消息减少",
                diagnosis="互动下降", strategy="减少主动",
                evidence_refs=[
                    {"message_id": "test_msg_1", "quote": "好的", "note": "简短回复"},
                    {"message_id": "test_msg_2", "quote": "嗯嗯", "note": "敷衍"},
                ],
                metric_snapshot={"composite": 0.32, "base_score": 0.45},
                data_window={"from_date": "2026-06-01", "to_date": "2026-06-29"},
                changed_from_previous="阶段从 平淡期 → 冷淡期",
            )["path"]
            assert path.is_file()
            import yaml
            with open(path, encoding="utf-8") as f:
                saved = yaml.safe_load(f)
            assert saved["stage"]["stage"] == "冷淡期"
            assert len(saved["evidence_refs"]) == 2
            assert saved["evidence_refs"][0]["message_id"] == "test_msg_1"
            assert saved["metric_snapshot"]["composite"] == 0.32
            assert saved["data_window"]["from_date"] == "2026-06-01"
            assert saved["changed_from_previous"] == "阶段从 平淡期 → 冷淡期"
            # 不带新字段的调用也应正常工作
            path2 = agent_save_analysis(result.person, stage="平淡期", confidence=0.5, reasoning="test")["path"]
            assert path2.is_file()
