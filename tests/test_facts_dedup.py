"""测试事实档案去重和覆盖告知功能。

覆盖：
- append_event 写侧去重（返回 (path, is_new) 元组）
- _dedup_timeline 读侧去重（时间线显示层去重）
- agent_save_analysis 覆盖返回（previous_info + changed_fields）
"""
import time

import pytest

from engine.agent.write import agent_save_analysis

NOW = int(time.time())


def _make_person(conn, name="测试客户", wxid="wxid_target"):
    """创建测试用 person。"""
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
    assert result.person is not None
    return result.person


# ═══════════════════════════════════════════════════════════════════
# append_event 写侧去重
# ═══════════════════════════════════════════════════════════════════

class TestAppendEventDedup:
    """append_event 返回 (path, is_new)，重复事件跳过写入。"""

    def test_first_write_is_new(self, tmp_db, test_config, tmp_path):
        person = _make_person(tmp_db)
        from unittest.mock import patch
        from engine.facts import people_archive

        facts_dir = tmp_path / "facts" / "people"
        facts_dir.mkdir(parents=True)
        with patch.object(people_archive, "FACTS_PEOPLE_DIR", facts_dir):
            path, is_new = people_archive.append_event(person, "2025-01-01", "断联", "7天未回复")
        assert is_new is True
        assert path.is_file()
        content = path.read_text(encoding="utf-8")
        assert content.count("- [2025-01-01] 断联: 7天未回复") == 1

    def test_duplicate_skipped(self, tmp_db, test_config, tmp_path):
        """同一事件第二次写入时 is_new=False，文件中不新增条目。"""
        person = _make_person(tmp_db)
        from unittest.mock import patch
        from engine.facts import people_archive

        facts_dir = tmp_path / "facts" / "people"
        facts_dir.mkdir(parents=True)
        with patch.object(people_archive, "FACTS_PEOPLE_DIR", facts_dir):
            path1, is_new1 = people_archive.append_event(person, "2025-01-01", "断联", "7天未回复")
            path2, is_new2 = people_archive.append_event(person, "2025-01-01", "断联", "7天未回复")
        assert is_new1 is True
        assert is_new2 is False
        assert path1 == path2
        content = path1.read_text(encoding="utf-8")
        assert content.count("- [2025-01-01] 断联: 7天未回复") == 1

    def test_different_events_not_deduped(self, tmp_db, test_config, tmp_path):
        """不同 date/type/detail 的事件不会被去重。"""
        person = _make_person(tmp_db)
        from unittest.mock import patch
        from engine.facts import people_archive

        facts_dir = tmp_path / "facts" / "people"
        facts_dir.mkdir(parents=True)
        with patch.object(people_archive, "FACTS_PEOPLE_DIR", facts_dir):
            _, is_new1 = people_archive.append_event(person, "2025-01-01", "断联", "7天未回复")
            _, is_new2 = people_archive.append_event(person, "2025-01-02", "恢复", "重新开始聊天")
            _, is_new3 = people_archive.append_event(person, "2025-01-01", "断联", "5天未回复")
        assert is_new1 is True
        assert is_new2 is True
        assert is_new3 is True

    def test_timestamp_refreshed_on_new_event(self, tmp_db, test_config, tmp_path):
        """写入新事件时 frontmatter updated_at 刷新。"""
        person = _make_person(tmp_db)
        from unittest.mock import patch
        from engine.facts import people_archive

        facts_dir = tmp_path / "facts" / "people"
        facts_dir.mkdir(parents=True)
        with patch.object(people_archive, "FACTS_PEOPLE_DIR", facts_dir):
            path, _ = people_archive.append_event(person, "2025-01-01", "断联", "7天未回复")
        content = path.read_text(encoding="utf-8")
        assert "updated_at:" in content
        assert "最后更新：" in content


# ═══════════════════════════════════════════════════════════════════
# _dedup_timeline 读侧去重
# ═══════════════════════════════════════════════════════════════════

class TestDedupTimeline:
    """_dedup_timeline 在显示层去重时间线事件条目。"""

    def test_removes_duplicate_entries(self):
        from engine.agent.evidence import _dedup_timeline
        content = (
            "## 关系时间线\n\n"
            "- [2025-01-01] 断联: 7天未回复\n"
            "- [2025-01-02] 恢复: 重新开始聊天\n"
            "- [2025-01-01] 断联: 7天未回复\n"
            "- [2025-01-03] 会面: 商务午餐\n"
        )
        result = _dedup_timeline(content)
        assert result.count("- [2025-01-01] 断联: 7天未回复") == 1
        assert result.count("- [2025-01-02] 恢复: 重新开始聊天") == 1
        assert result.count("- [2025-01-03] 会面: 商务午餐") == 1

    def test_preserves_non_event_lines(self):
        """非事件条目（如 ### 日期标题）不受去重影响。"""
        from engine.agent.evidence import _dedup_timeline
        content = (
            "### 2025-01-01\n"
            "- 地点：餐厅\n"
            "- [2025-01-01] 断联: 7天未回复\n"
            "- [2025-01-01] 断联: 7天未回复\n"
            "### 2025-01-02\n"
            "- 评分：4/5\n"
        )
        result = _dedup_timeline(content)
        assert result.count("- [2025-01-01] 断联: 7天未回复") == 1
        assert result.count("### 2025-01-01") == 1
        assert result.count("### 2025-01-02") == 1
        assert result.count("- 地点：餐厅") == 1
        assert result.count("- 评分：4/5") == 1

    def test_empty_content(self):
        from engine.agent.evidence import _dedup_timeline
        assert _dedup_timeline("") == ""

    def test_no_duplicates_unchanged(self):
        from engine.agent.evidence import _dedup_timeline
        content = "- [2025-01-01] 断联: 7天\n- [2025-01-02] 恢复: 重新聊天\n"
        result = _dedup_timeline(content)
        assert result == content


# ═══════════════════════════════════════════════════════════════════
# agent_save_analysis 覆盖返回信息
# ═══════════════════════════════════════════════════════════════════

class TestSaveAnalysisOverwriteInfo:
    """agent_save_analysis 返回 dict 含 previous_info 和 changed_fields。"""

    def test_first_write_no_previous(self, tmp_db, test_config, tmp_path):
        """首次写入时 previous_info 为 None，changed_fields 为空。"""
        person = _make_person(tmp_db)
        import engine.config as config_mod
        orig_dir = config_mod.OUTPUTS_ANALYSIS_DIR
        config_mod.OUTPUTS_ANALYSIS_DIR = tmp_path / "analysis"
        try:
            result = agent_save_analysis(
                person, stage="接触期", confidence=0.5, reasoning="初始",
                diagnosis="诊断1", strategy="策略1",
            )
            assert isinstance(result, dict)
            assert result["previous_info"] is None
            assert result["changed_fields"] == []
            assert result["path"].is_file()
            assert result["history_path"].is_file()
        finally:
            config_mod.OUTPUTS_ANALYSIS_DIR = orig_dir

    def test_overwrite_reports_previous_info(self, tmp_db, test_config, tmp_path):
        """覆盖写入时返回旧版本信息。"""
        person = _make_person(tmp_db)
        import engine.config as config_mod
        orig_dir = config_mod.OUTPUTS_ANALYSIS_DIR
        config_mod.OUTPUTS_ANALYSIS_DIR = tmp_path / "analysis"
        try:
            agent_save_analysis(
                person, stage="接触期", confidence=0.5, reasoning="初始",
                diagnosis="诊断1", strategy="策略1",
            )
            result = agent_save_analysis(
                person, stage="谈判期", confidence=0.8, reasoning="初始",
                diagnosis="诊断1", strategy="策略1",
            )
            assert result["previous_info"] is not None
            assert "path" in result["previous_info"]
            assert "size" in result["previous_info"]
            assert "generated_at" in result["previous_info"]
            assert result["previous_info"]["size"] > 0
        finally:
            config_mod.OUTPUTS_ANALYSIS_DIR = orig_dir

    def test_changed_fields_detected(self, tmp_db, test_config, tmp_path):
        """变更字段被正确识别。"""
        person = _make_person(tmp_db)
        import engine.config as config_mod
        orig_dir = config_mod.OUTPUTS_ANALYSIS_DIR
        config_mod.OUTPUTS_ANALYSIS_DIR = tmp_path / "analysis"
        try:
            agent_save_analysis(
                person, stage="接触期", confidence=0.5, reasoning="依据A",
                diagnosis="诊断A", strategy="策略A",
            )
            result = agent_save_analysis(
                person, stage="谈判期", confidence=0.8, reasoning="依据A",
                diagnosis="诊断B", strategy="策略A",
            )
            assert "stage" in result["changed_fields"]
            assert "confidence" in result["changed_fields"]
            assert "diagnosis" in result["changed_fields"]
            assert "reasoning" not in result["changed_fields"]
            assert "strategy" not in result["changed_fields"]
        finally:
            config_mod.OUTPUTS_ANALYSIS_DIR = orig_dir

    def test_no_change_when_same_data(self, tmp_db, test_config, tmp_path):
        """相同数据再次写入时 changed_fields 为空。"""
        person = _make_person(tmp_db)
        import engine.config as config_mod
        orig_dir = config_mod.OUTPUTS_ANALYSIS_DIR
        config_mod.OUTPUTS_ANALYSIS_DIR = tmp_path / "analysis"
        try:
            agent_save_analysis(
                person, stage="接触期", confidence=0.5, reasoning="依据A",
                diagnosis="诊断A", strategy="策略A",
            )
            result = agent_save_analysis(
                person, stage="接触期", confidence=0.5, reasoning="依据A",
                diagnosis="诊断A", strategy="策略A",
            )
            assert result["changed_fields"] == []
            assert result["previous_info"] is not None
        finally:
            config_mod.OUTPUTS_ANALYSIS_DIR = orig_dir

    def test_history_path_created(self, tmp_db, test_config, tmp_path):
        """history_path 指向 history/ 目录下的带时间戳文件。"""
        person = _make_person(tmp_db)
        import engine.config as config_mod
        orig_dir = config_mod.OUTPUTS_ANALYSIS_DIR
        config_mod.OUTPUTS_ANALYSIS_DIR = tmp_path / "analysis"
        try:
            result = agent_save_analysis(
                person, stage="接触期", confidence=0.5, reasoning="初始",
                diagnosis="诊断", strategy="策略",
            )
            assert result["history_path"].is_file()
            assert result["history_path"].parent.name == "history"
        finally:
            config_mod.OUTPUTS_ANALYSIS_DIR = orig_dir
