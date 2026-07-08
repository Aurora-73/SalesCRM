"""Agent 工具集 — Claude Code 直接调用的数据工具。

所有函数返回 str（Markdown）或 dict（结构化数据），Agent 直接读取后自行分析。

用法示例（在 Claude Code Bash 中）：
    cd E:/Code/SalesCRM && python -c "
    from engine.tools import brief, chat, wiki_search
    print(brief('张三', compact=True))
    print(chat('张三', recent=50))
    "

函数签名统一规则：
    - 接收人名的函数：第一个参数是 name (str)
    - 内部自动处理 conn/config/person 的解析
    - 调用者不需要关心数据库连接和身份解析
"""

from engine.agent.core import _get_conn, _resolve_person
from engine.agent.brief import agent_brief as _agent_brief
from engine.agent.brief import agent_brief_data as _agent_brief_data
from engine.agent.chat import agent_chat as _agent_chat
from engine.agent.chat import agent_chat_data as _agent_chat_data
from engine.agent.context import query_message_context
from engine.agent.evidence import agent_evidence as _agent_evidence
from engine.agent.material import agent_material_search as _agent_material_search
from engine.agent.write import (
    agent_save_analysis as _agent_save_analysis,
    agent_save_from_markdown as _agent_save_from_markdown,
)
from engine.agent.moments import sync_moments_to_archive as _sync_moments_to_archive

# write.py 中的函数内部自行管理 conn/config，直接透传
from engine.agent.write import agent_note as note
from engine.agent.write import agent_date as date
from engine.agent.write import agent_evaluate as evaluate
from engine.agent.write import agent_events as events

# report.py / identity_ops.py / sync_agent.py / moments.py 的函数签名已兼容，直接透传
from engine.agent.report import agent_metrics as metrics
from engine.agent.report import agent_rank as rank
from engine.agent.report import agent_status as status
from engine.agent.report import agent_weekly as weekly
from engine.agent.report import agent_compare_analysis as compare_analysis
from engine.agent.material import agent_material_show as wiki_show
from engine.agent.identity_ops import agent_contact as contact
from engine.agent.identity_ops import agent_exclude as exclude
from engine.agent.identity_ops import agent_failure as failure
from engine.agent.identity_ops import agent_sticker as sticker
from engine.agent.sync_agent import agent_sync as sync
from engine.agent.sync_agent import sync_person
from engine.agent.moments import moments_stats
from engine.agent.maintain import maintain_candidates, format_candidates

from engine.formulas import (
    formula_params,
    formula_ivi,
    formula_spe,
    formula_ews,
    formula_is,
    formula_gap_effect,
    formula_eev,
    formula_cs,
    formula_action,
    sales_params,
    sales_bq,
    sales_bsp,
    sales_bws,
    sales_pv,
    sales_action,
)


def _resolve(name: str):
    """内部辅助：获取 (conn, config, person)。"""
    conn, config = _get_conn()
    person = _resolve_person(conn, name)
    if not person:
        conn.close()
        raise ValueError(f"未找到联系人: {name}")
    return conn, config, person


# ── 包装函数（自动解析人名 → conn/config/person）────────────────────

def brief(name: str, compact: bool = False) -> str:
    """全局视图：事实+指标+事件+信号+Wiki推荐。"""
    conn, config, person = _resolve(name)
    try:
        return _agent_brief(conn, config, person, compact=compact)
    finally:
        conn.close()


def chat(name: str, *, recent: int = 50, from_date: str | None = None,
         to_date: str | None = None, keyword: str | None = None,
         context_lines: int = 0) -> str:
    """聊天记录（按日期分组，已标注"我"/对方名字）。"""
    conn, config, person = _resolve(name)
    try:
        return _agent_chat(conn, config, person, recent=recent,
                           from_date=from_date, to_date=to_date,
                           keyword=keyword, context_lines=context_lines)
    finally:
        conn.close()


def evidence(name: str, section: str = "all", since_date: str | None = None) -> str:
    """事实档案（timeline/evaluations/notes/dates/all）。"""
    conn, config, person = _resolve(name)
    try:
        return _agent_evidence(conn, config, person, section=section,
                               since_date=since_date)
    finally:
        conn.close()


def wiki_search(query: str) -> str:
    """跨 Wiki/分析/KB 搜索。"""
    conn, config = _get_conn()
    try:
        return _agent_material_search(conn, config, query)
    finally:
        conn.close()


def save_analysis(name: str, **kwargs) -> dict:
    """保存分析结论到 YAML。返回 dict 含 path/previous_info/changed_fields/history_path。"""
    conn, config, person = _resolve(name)
    try:
        result = _agent_save_analysis(person, **kwargs)
        return {
            "path": str(result["path"]),
            "previous_info": result["previous_info"],
            "changed_fields": result["changed_fields"],
            "history_path": str(result["history_path"]),
        }
    finally:
        conn.close()


def save_from_markdown(name: str, markdown_text: str) -> str:
    """从结构化 Markdown 保存分析。"""
    conn, config, person = _resolve(name)
    try:
        return str(_agent_save_from_markdown(person, markdown_text))
    finally:
        conn.close()


def chat_data(name: str, *, recent: int = 50, from_date: str | None = None,
              to_date: str | None = None, keyword: str | None = None,
              context_lines: int = 0) -> dict:
    """结构化聊天查询 — 返回 dict 含 messages 列表及元信息。"""
    conn, config, person = _resolve(name)
    try:
        return _agent_chat_data(conn, config, person, recent=recent,
                                from_date=from_date, to_date=to_date,
                                keyword=keyword, context_lines=context_lines)
    finally:
        conn.close()


def brief_data(name: str) -> dict:
    """结构化摘要 — 返回 dict 含 identity/metrics/events/signals/recent_messages 等。"""
    conn, config, person = _resolve(name)
    try:
        return _agent_brief_data(conn, config, person)
    finally:
        conn.close()


def message_context_data(message_ids: list[str], before: int = 20, after: int = 20) -> dict:
    """根据消息 ID 获取前后上下文消息（不跨会话）。"""
    conn, config = _get_conn()
    try:
        return query_message_context(conn, message_ids, before=before, after=after,
                                     my_wxid=config.my_wxid)
    finally:
        conn.close()


def rank_data() -> dict:
    """结构化排名查询 — 返回 dict 含排名列表。"""
    from engine.analyzers.ranker import compute_rankings
    conn, config = _get_conn()
    try:
        ranking = compute_rankings(conn, config)
        return ranking.to_yaml()
    finally:
        conn.close()


def status_data(name: str) -> dict:
    """结构化状态概览 — 返回精简的状态快照。

    与 person_metrics 的区别：
    - person_status：快速了解当前状态（信号等级 + 消息统计 + 趋势），字段少
    - person_metrics：深入分析指标详情（所有 metrics 展开），字段多
    """
    from engine.analyzers.metrics import compute_metrics_for_contact
    conn, config = _get_conn()
    try:
        person = _resolve_person(conn, name)
        if not person:
            return {"error": "PERSON_NOT_FOUND", "message": f"未找到联系人: {name}"}
        if not person.accounts:
            return {"error": "PERSON_NOT_FOUND", "message": f"未找到联系人: {name}"}
        result = {
            "person_id": person.id,
            "display_name": person.display_name,
            "account_count": len(person.accounts),
            "accounts": [],
        }
        for account in person.accounts:
            wxid = account.conversation_id or account.wxid
            if not wxid:
                continue
            msg_row = conn.execute("SELECT COUNT(*) AS cnt FROM messages WHERE conversation_id = ?", (wxid,)).fetchone()
            message_count = msg_row["cnt"] if msg_row else 0
            metrics = compute_metrics_for_contact(conn, config, wxid, account.display_name or person.display_name)
            result["accounts"].append({
                "wxid": wxid,
                "display_name": account.display_name,
                "message_count": message_count,
                "composite": round(metrics.composite, 4),
                "signal_level": metrics.signal_level,
                "interaction_pattern": metrics.interaction_pattern,
                "recent_days": round(metrics.recent.raw, 1),
                "trend": round(metrics.trend.normalized - 0.5, 4),
                "neediness_penalty": round(metrics.neediness_penalty, 4),
            })
        return result
    finally:
        conn.close()


def wiki_search_data(query: str, limit: int = 5) -> dict:
    """结构化 Wiki 搜索 — 返回 dict 含搜索结果列表。"""
    conn, config = _get_conn()
    try:
        results: list[dict] = []
        query_terms = query.lower().split()

        from engine.agent.material import _search_wiki, _search_analysis, _search_kb
        _search_wiki(query_terms, results)
        _search_analysis(query_terms, results)
        _search_kb(query_terms, results)

        results.sort(key=lambda r: (r.get("priority", 99), -r.get("score", 0)))
        return {
            "query": query,
            "total_results": len(results),
            "results": results[:limit],
        }
    finally:
        conn.close()


def wiki_context_data(
    queries: list[str],
    task_type: str = "analyze",
    stage: str = "",
    focus: str = "",
    max_chars: int = 8000,
    max_pages: int = 8,
) -> dict:
    """批量构建 Wiki 上下文 — 多查询合并 + 阶段过滤 + 焦点加权 + 格式化返回。

    与 wiki_search/wik_read 的区别：
    - wiki_context 一次返回 prompt-ready 格式化段落（合并去重 + 预算裁剪）
    - wiki_search 返回候选列表（需逐条 wiki_read）
    - wiki_read 读取单页全文

    Returns:
        dict: {
            "prompt_section": str,  # 可嵌入推理的 Markdown 段落
            "meta": {
                "hit_pages": int, "returned_pages": int,
                "deduped": int, "total_chars": int,
                "low_confidence": bool, "stage_filter": str, "focus": str,
            },
            "page_list": [{"title", "path", "page_type", "score", "summary"}, ...]
        }
    """
    from engine.knowledge.wiki_index import WikiIndex
    from engine.knowledge.wiki_retriever import WikiRetriever, WikiSnippet
    from engine.knowledge.wiki_context import format_wiki_for_prompt

    if len(queries) > 5:
        queries = queries[:5]

    index = WikiIndex()
    if not index.load() or index.is_empty:
        return {
            "prompt_section": (
                "## 本地知识库参考（未加载）\n"
                "Wiki 索引为空或加载失败。请检查 Wiki 目录配置。\n"
            ),
            "meta": {
                "hit_pages": 0, "returned_pages": 0, "deduped": 0,
                "total_chars": 0, "low_confidence": True,
                "stage_filter": stage, "focus": focus,
            },
            "page_list": [],
        }

    retriever = WikiRetriever(index)
    all_snippets: dict[str, WikiSnippet] = {}
    total_raw_hits = 0

    for query in queries:
        if not query.strip():
            continue
        snippets = retriever.retrieve(
            query_text=query,
            task_type=task_type,
            stage=stage,
            focus=focus,
            max_chars=max_chars,
            max_pages=max_pages,
        )
        total_raw_hits += len(snippets)
        for s in snippets:
            if s.path not in all_snippets or s.score > all_snippets[s.path].score:
                all_snippets[s.path] = s

    sorted_snippets = sorted(all_snippets.values(), key=lambda s: s.score, reverse=True)
    final_snippets = []
    total_chars = 0
    for s in sorted_snippets:
        if len(final_snippets) >= max_pages:
            break
        if total_chars + len(s.content) > max_chars and final_snippets:
            break
        final_snippets.append(s)
        total_chars += len(s.content)

    prompt_section = format_wiki_for_prompt(final_snippets)

    page_list = []
    for s in final_snippets:
        raw_path = s.path
        if raw_path.startswith("docs/"):
            path = raw_path
        elif raw_path.startswith("wiki/"):
            path = f"docs/wiki/{raw_path}"
        else:
            path = f"docs/wiki/wiki/{raw_path}"
        page_list.append({
            "title": s.title,
            "path": path,
            "page_type": s.page_type,
            "score": s.score,
            "summary": s.summary,
        })

    return {
        "prompt_section": prompt_section,
        "meta": {
            "hit_pages": total_raw_hits,
            "returned_pages": len(final_snippets),
            "deduped": total_raw_hits - len(all_snippets),
            "total_chars": total_chars,
            "low_confidence": not final_snippets or max(s.score for s in final_snippets) < 5,
            "stage_filter": stage,
            "focus": focus,
        },
        "page_list": page_list,
    }


def timeline(name: str, max_events: int = 30, categories: list[str] | None = None) -> dict:
    """结构化时间线查询 — 返回 dict 含客户事件列表。"""
    from engine.analyzers.events import compute_timeline, timeline_to_dict
    conn, config = _get_conn()
    try:
        person = _resolve_person(conn, name)
        if not person:
            return {"error": "PERSON_NOT_FOUND", "message": f"未找到联系人: {name}"}
        events = compute_timeline(conn, person, max_events=max_events, categories=categories)
        return {
            "person_id": person.id,
            "display_name": person.display_name,
            "events": timeline_to_dict(events),
        }
    finally:
        conn.close()


def stage_data(name: str) -> dict:
    """销售阶段自动识别 — 基于指标+事件+失败档案推断当前销售阶段。

    返回 StageState 字典：current_stage / next_stage / advancement_signals /
    blockers / is_stagnant / entered_at / days_in_current_stage。
    """
    from engine.analyzers.stage_recognizer import recognize_stage, get_stage_summary
    from engine.analyzers.metrics import compute_metrics_for_contact
    conn, config = _get_conn()
    try:
        person = _resolve_person(conn, name)
        if not person:
            return {"error": "PERSON_NOT_FOUND", "message": f"未找到联系人: {name}"}
        wxids = [acc.conversation_id or acc.wxid for acc in person.accounts if acc.conversation_id or acc.wxid]
        if not wxids:
            return {"error": "NO_CONVERSATION_ID", "message": f"联系人 {name} 没有会话 ID"}

        metrics = compute_metrics_for_contact(conn, config, wxids[0], person.display_name)
        stage = recognize_stage(conn, metrics, wxids[0], person.display_name)
        result = get_stage_summary(stage)
        result["person_id"] = person.id
        result["display_name"] = person.display_name
        return result
    finally:
        conn.close()


def signals(name: str) -> dict:
    """结构化信号查询 — 返回 dict 含检测到的信号。"""
    from engine.agent.signals import _detect_signals, detect_manipulation_signals, _detect_moments_chat_signals, _query_signal_messages
    conn, config = _get_conn()
    try:
        person = _resolve_person(conn, name)
        if not person:
            return {"error": "PERSON_NOT_FOUND", "message": f"未找到联系人: {name}"}
        wxids = [acc.conversation_id or acc.wxid for acc in person.accounts if acc.conversation_id or acc.wxid]
        messages = _query_signal_messages(conn, wxids, config.my_wxid)
        basic_signals = _detect_signals(messages)
        manipulation_signals = detect_manipulation_signals(messages, config.my_wxid)
        moments_signals = {}
        for acc in person.accounts:
            wxid = acc.conversation_id or acc.wxid
            if wxid:
                acc_signals = _detect_moments_chat_signals(
                    conn, wxid, config.my_wxid, acc.display_name or person.display_name
                )
                moments_signals.update(acc_signals)
        return {
            "person_id": person.id,
            "display_name": person.display_name,
            "basic_signals": basic_signals,
            "manipulation_signals": manipulation_signals,
            "moments_signals": moments_signals,
        }
    finally:
        conn.close()


def sync_moments(name: str) -> str:
    """同步朋友圈互动到事实档案。"""
    conn, config, person = _resolve(name)
    try:
        return _sync_moments_to_archive(conn, config, person)
    finally:
        conn.close()


def check_keys() -> str:
    """检查 WCD 密钥是否已缓存（account_keys.json）。"""
    from engine.importers.wcd_client import WCDClient
    conn, config = _get_conn()
    try:
        if config.weflow.backend != "wcd":
            return "当前后端不是 WCD，无需检查密钥缓存。"
        client = WCDClient(
            base_url=config.weflow.base_url,
            decrypted_db_dir=config.weflow.decrypted_db_dir or None,
        )
        result = client.check_cached_keys()
        if result.get("cached"):
            return (
                f"密钥已缓存: {', '.join(result.get('accounts', []))}\n"
                f"路径: {result.get('path', 'N/A')}"
            )
        return f"密钥未缓存: {result.get('reason', '未知原因')}"
    finally:
        conn.close()


def fetch_keys(wechat_install_path: str | None = None) -> str:
    """⚠️ 获取微信数据库密钥（会重启微信，不建议使用）。

    此操作会：
    1. 强制关闭微信进程
    2. 重新启动微信
    3. 要求用户在 60 秒内完成扫码登录
    4. 频繁调用可能导致微信账号异常

    正确做法：确保 output/account_keys.json 存在，密钥会自动加载。
    """
    from engine.importers.wcd_client import WCDClient
    conn, config = _get_conn()
    try:
        if config.weflow.backend != "wcd":
            return "当前后端不是 WCD，无法获取密钥。"
        client = WCDClient(
            base_url=config.weflow.base_url,
            token=config.weflow.token,
            timeout=config.weflow.timeout,
            decrypted_db_dir=config.weflow.decrypted_db_dir or None,
        )
        result = client.fetch_keys(wechat_install_path=wechat_install_path)
        if result.get("status") == 0:
            data = result.get("data", {})
            return (
                f"密钥获取成功（但不建议频繁使用此方法）\n"
                f"db_key: {data.get('db_key', 'N/A')[:16]}...\n"
                f"请将密钥保存到 account_keys.json 以避免重复获取。"
            )
        return f"密钥获取失败: {result.get('errmsg', '未知错误')}"
    finally:
        conn.close()


__all__ = [
    # 只读
    "brief", "chat", "evidence", "metrics", "rank", "status",
    "wiki_search", "wiki_show",
    # 只读（结构化）
    "brief_data", "chat_data", "message_context_data",
    "rank_data", "status_data", "wiki_search_data", "wiki_context_data",
    "timeline", "signals", "stage_data",
    # 写入
    "note", "date", "evaluate", "events",
    "save_analysis", "save_from_markdown",
    "contact", "exclude", "failure", "sticker",
    # 同步
    "sync", "sync_person", "sync_moments",
    # 朋友圈
    "moments_stats",
    # 周报
    "weekly",
    # 对比
    "compare_analysis",
    # 维持关系
    "maintain_candidates", "format_candidates",
    # 密钥管理
    "check_keys", "fetch_keys",
    # 战态公式
    "formula_params", "formula_ivi", "formula_spe", "formula_ews",
    "formula_is", "formula_gap_effect", "formula_eev", "formula_cs",
    "formula_action",
    # 销售决策公式
    "sales_params", "sales_bq", "sales_bsp", "sales_bws",
    "sales_pv", "sales_action",
]
