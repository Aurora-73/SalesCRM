"""身份解析单元测试。

覆盖 bootstrap_identity/resolve_contact/get_person/merge_people/
link_account/add_alias/normalize_alias 等核心函数。
"""
import time

import pytest

from engine.identity import (
    IdentityAccount,
    IdentityPerson,
    ResolveResult,
    bootstrap_identity,
    resolve_contact,
    get_person,
    merge_people,
    link_account,
    add_alias,
    set_display_name,
    search_people,
)
from engine.identity.directory import normalize_alias, _person_id_for_wxid


# ── normalize_alias ──────────────────────────────────────────────────────────

class TestNormalizeAlias:
    def test_lowercase(self):
        assert normalize_alias("ABC") == "abc"

    def test_strip_spaces(self):
        assert normalize_alias("  hello  ") == "hello"

    def test_remove_inner_spaces(self):
        assert normalize_alias("hello world") == "helloworld"

    def test_mixed_case_with_spaces(self):
        assert normalize_alias("  XiAo Xi  ") == "xiaoxi"

    def test_chinese(self):
        assert normalize_alias("小溪") == "小溪"

    def test_empty(self):
        assert normalize_alias("") == ""


# ── _person_id_for_wxid ──────────────────────────────────────────────────────

class TestPersonIdForWxid:
    def test_deterministic(self):
        """同一 wxid 始终生成相同 person_id。"""
        pid1 = _person_id_for_wxid("wxid_abc123")
        pid2 = _person_id_for_wxid("wxid_abc123")
        assert pid1 == pid2

    def test_format(self):
        """person_id 格式为 person_{8位hex}。"""
        pid = _person_id_for_wxid("wxid_test")
        assert pid.startswith("person_")
        assert len(pid) == len("person_") + 8

    def test_different_wxid(self):
        """不同 wxid 生成不同 person_id。"""
        assert _person_id_for_wxid("wxid_a") != _person_id_for_wxid("wxid_b")


# ── bootstrap_identity ───────────────────────────────────────────────────────

class TestBootstrap:
    def test_creates_people_and_accounts(self, tmp_db, setup_contacts, now_ts):
        """bootstrap 从 contacts/conversations 创建 person 和 account。"""
        setup_contacts("wxid_test1", "小溪", remark="溪溪")
        result = bootstrap_identity(tmp_db)
        assert result["people"] >= 1
        assert result["accounts"] >= 1

    def test_idempotent(self, tmp_db, setup_contacts, now_ts):
        """重复调用不会创建重复记录。"""
        setup_contacts("wxid_test1", "小溪")
        r1 = bootstrap_identity(tmp_db)
        r2 = bootstrap_identity(tmp_db)
        assert r2["people"] == 0  # 第二次不创建新 person
        assert r2["accounts"] == 0

    def test_creates_aliases(self, tmp_db, setup_contacts, now_ts):
        """bootstrap 自动创建别名。"""
        setup_contacts("wxid_test1", "小溪", remark="溪溪")
        result = bootstrap_identity(tmp_db)
        assert result["aliases"] >= 1


# ── resolve_contact ──────────────────────────────────────────────────────────

class TestResolveContact:
    def test_by_person_id(self, tmp_db, setup_people, now_ts):
        """按 person_id 精确匹配。"""
        setup_people("person_abcd1234", "小溪", "wxid_xiaoxi")
        result = resolve_contact(tmp_db, "person_abcd1234")
        assert result.person is not None
        assert result.person.id == "person_abcd1234"
        assert result.matched_by == "person_id"

    def test_by_wxid(self, tmp_db, setup_people, now_ts):
        """按 wxid 精确匹配。"""
        setup_people("person_abcd1234", "小溪", "wxid_xiaoxi")
        result = resolve_contact(tmp_db, "wxid_xiaoxi")
        assert result.person is not None
        assert result.person.display_name == "小溪"
        assert result.matched_by == "account"

    def test_by_display_name(self, tmp_db, setup_people, now_ts):
        """按显示名精确匹配（通过别名）。"""
        pid = "person_abcd1234"
        setup_people(pid, "小溪", "wxid_xiaoxi")
        # bootstrap 会创建 display_name 别名，但 setup_people 不会
        # 需要手动添加别名
        add_alias(tmp_db, pid, "display_name", "小溪")
        result = resolve_contact(tmp_db, "小溪")
        assert result.person is not None
        assert result.person.display_name == "小溪"

    def test_fuzzy_search(self, tmp_db, setup_people, now_ts):
        """模糊搜索包含关键词的别名。"""
        pid = "person_abcd1234"
        setup_people(pid, "小溪同学", "wxid_xiaoxi")
        add_alias(tmp_db, pid, "manual", "小溪同学")
        result = resolve_contact(tmp_db, "小溪")
        assert result.person is not None
        assert result.matched_by == "alias:fuzzy"

    def test_not_found(self, tmp_db):
        """查不到返回 ResolveResult，person=None。"""
        result = resolve_contact(tmp_db, "不存在的人")
        assert result.person is None

    def test_empty_query(self, tmp_db):
        """空查询返回 None。"""
        result = resolve_contact(tmp_db, "")
        assert result.person is None

    def test_whitespace_query(self, tmp_db):
        """空白查询返回 None。"""
        result = resolve_contact(tmp_db, "   ")
        assert result.person is None


# ── get_person ───────────────────────────────────────────────────────────────

class TestGetPerson:
    def test_returns_person_with_accounts(self, tmp_db, setup_people, now_ts):
        """返回的 person 包含 accounts 列表。"""
        setup_people("person_abcd1234", "小溪", "wxid_xiaoxi")
        person = get_person(tmp_db, "person_abcd1234")
        assert person is not None
        assert person.id == "person_abcd1234"
        assert person.display_name == "小溪"
        assert len(person.accounts) >= 1
        assert person.accounts[0].wxid == "wxid_xiaoxi"

    def test_not_found(self, tmp_db):
        """不存在的 person_id 返回 None。"""
        assert get_person(tmp_db, "person_nonexistent") is None

    def test_frozen_dataclass(self, tmp_db, setup_people, now_ts):
        """IdentityPerson 是 frozen 的，不能修改。"""
        setup_people("person_abcd1234", "小溪", "wxid_xiaoxi")
        person = get_person(tmp_db, "person_abcd1234")
        with pytest.raises(AttributeError):
            person.display_name = "新名字"


# ── merge_people ─────────────────────────────────────────────────────────────

class TestMergePeople:
    def test_merge_transfers_accounts(self, tmp_db, setup_people, now_ts):
        """合并后 account 转移到 keep_person。"""
        setup_people("person_keep", "小溪", "wxid_xiaoxi1")
        setup_people("person_merge", "溪溪", "wxid_xiaoxi2")
        success = merge_people(tmp_db, "person_keep", "person_merge")
        assert success is True
        person = get_person(tmp_db, "person_keep")
        wxids = {a.wxid for a in person.accounts}
        assert "wxid_xiaoxi1" in wxids
        assert "wxid_xiaoxi2" in wxids

    def test_merge_deletes_merged_person(self, tmp_db, setup_people, now_ts):
        """合并后 merge_person 被删除。"""
        setup_people("person_keep", "小溪", "wxid_xiaoxi1")
        setup_people("person_merge", "溪溪", "wxid_xiaoxi2")
        merge_people(tmp_db, "person_keep", "person_merge")
        assert get_person(tmp_db, "person_merge") is None

    def test_merge_same_person_returns_false(self, tmp_db, setup_people, now_ts):
        """合并自己到自己返回 False。"""
        setup_people("person_same", "小溪", "wxid_xiaoxi")
        assert merge_people(tmp_db, "person_same", "person_same") is False

    def test_merge_nonexistent_returns_false(self, tmp_db, setup_people, now_ts):
        """合并不存在的人返回 False。"""
        setup_people("person_keep", "小溪", "wxid_xiaoxi")
        assert merge_people(tmp_db, "person_keep", "person_ghost") is False


# ── link_account ─────────────────────────────────────────────────────────────

class TestLinkAccount:
    def test_link_new_account(self, tmp_db, setup_people, setup_contacts, now_ts):
        """将新 wxid 链接到已有人物。"""
        setup_people("person_abcd1234", "小溪", "wxid_xiaoxi1")
        setup_contacts("wxid_xiaoxi2", "小溪2号")
        success = link_account(tmp_db, "person_abcd1234", "wxid_xiaoxi2")
        assert success is True
        person = get_person(tmp_db, "person_abcd1234")
        wxids = {a.wxid for a in person.accounts}
        assert "wxid_xiaoxi2" in wxids

    def test_link_nonexistent_person(self, tmp_db, setup_contacts, now_ts):
        """链接到不存在的 person 返回 False。"""
        setup_contacts("wxid_test", "测试")
        assert link_account(tmp_db, "person_ghost", "wxid_test") is False


# ── add_alias ────────────────────────────────────────────────────────────────

class TestAddAlias:
    def test_add_manual_alias(self, tmp_db, setup_people, now_ts):
        """手动添加别名。"""
        setup_people("person_abcd1234", "小溪", "wxid_xiaoxi")
        success = add_alias(tmp_db, "person_abcd1234", "manual", "溪溪")
        assert success is True
        person = get_person(tmp_db, "person_abcd1234")
        alias_values = [a["value"] for a in person.aliases]
        assert "溪溪" in alias_values

    def test_add_alias_nonexistent_person(self, tmp_db):
        """给不存在的人添加别名返回 False。"""
        assert add_alias(tmp_db, "person_ghost", "manual", "test") is False

    def test_resolve_by_added_alias(self, tmp_db, setup_people, now_ts):
        """通过手动添加的别名能找到人。"""
        setup_people("person_abcd1234", "小溪", "wxid_xiaoxi")
        add_alias(tmp_db, "person_abcd1234", "manual", "溪溪")
        result = resolve_contact(tmp_db, "溪溪")
        assert result.person is not None
        assert result.person.id == "person_abcd1234"


# ── set_display_name ─────────────────────────────────────────────────────────

class TestSetDisplayName:
    def test_update_name(self, tmp_db, setup_people, now_ts):
        """更新显示名。"""
        setup_people("person_abcd1234", "小溪", "wxid_xiaoxi")
        success = set_display_name(tmp_db, "person_abcd1234", "新名字")
        assert success is True
        person = get_person(tmp_db, "person_abcd1234")
        assert person.display_name == "新名字"

    def test_nonexistent_person(self, tmp_db):
        """更新不存在的人返回 False。"""
        assert set_display_name(tmp_db, "person_ghost", "test") is False


# ── search_people ────────────────────────────────────────────────────────────

class TestSearchPeople:
    def test_search_finds_person(self, tmp_db, setup_people, now_ts):
        """search_people 能找到人。"""
        setup_people("person_abcd1234", "小溪", "wxid_xiaoxi")
        add_alias(tmp_db, "person_abcd1234", "manual", "小溪")
        result = search_people(tmp_db, "小溪")
        assert result.person is not None
