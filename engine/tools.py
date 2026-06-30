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


def save_analysis(name: str, **kwargs) -> str:
    """保存分析结论到 YAML。"""
    conn, config, person = _resolve(name)
    try:
        return str(_agent_save_analysis(person, **kwargs))
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
