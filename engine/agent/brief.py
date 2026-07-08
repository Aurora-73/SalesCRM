"""摘要视图 — agent_brief。"""
from __future__ import annotations

import re
import sqlite3
import yaml
from datetime import datetime, timezone, timedelta

from engine.config import Config, OUTPUTS_ANALYSIS_DIR, slug_display_name
from engine.identity import IdentityPerson
from engine.agent.core import _build_cross_refs, _extract_sections
from engine.agent.snapshot import _select_important_messages, _generate_monthly_summary


_BEIJING_TZ = timezone(timedelta(hours=8))


def _ts_to_beijing(ts):
    """Unix 秒级时间戳转北京时间字符串（内部存储仍为整数，接口处转为可读格式）。"""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=_BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def agent_brief(conn: sqlite3.Connection, config: Config, person: IdentityPerson, *, compact: bool = False) -> str:
    """全局摘要视图 — 基于 agent_brief_data 的数据生成 Markdown 格式。"""
    from engine.agent.context import ContextBuilder

    data = agent_brief_data(conn, config, person)["data"]

    parts = [f"# Brief: {person.display_name}\n"]
    # Block 1: 事实快照
    parts.append("# 事实快照\n")
    identity = data["identity"]
    accounts = ", ".join(a["wxid"] for a in identity["accounts"])
    parts.append(f"## 身份\n- person_id: {identity['person_id']}\n- display_name: {identity['display_name']}\n- accounts: {accounts}\n")
    stats = data["message_stats"]
    first_ts = stats.get("first_ts")
    last_ts = stats.get("last_ts")
    first_str = datetime.fromtimestamp(first_ts).strftime("%Y-%m-%d") if first_ts else "N/A"
    last_str = datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d") if last_ts else "N/A"
    parts.append(f"## 数据可信度\n- 水平: {data.get('data_confidence', '未知')}\n- 总消息: {stats.get('total', 0)}\n- 首条: {first_str}\n- 末条: {last_str}\n")
    m = data["metrics"]
    if m:
        parts.append("## 指标\n")
        parts.append("| 指标 | 值 | 置信度 |")
        parts.append("|------|-----|--------|")
        parts.append(f"| Composite | {m.get('composite', 0):.4f} | — |")
        parts.append(f"| Base Score | {m.get('base_score', 0):.4f} | — |")
        parts.append(f"| Feedback | {m.get('fback', 0):.4f} | {m.get('fback_confidence', 0):.2f} |")
        parts.append(f"| Response Latency | {m.get('rlatency', 0):.4f} | — |")
        parts.append(f"| Quality Score | {m.get('qscore', 0):.4f} | — |")
        parts.append(f"| Engagement | {m.get('escore', 0):.4f} | — |")
        parts.append(f"| Signal Level | {m.get('signal_level', '未知')} | — |")
        parts.append("")
    trend = data.get("ranking_trend", {})
    if trend:
        parts.append(f"## 排名趋势\n- Rank: #{trend.get('rank', '?')} (delta: {trend.get('delta_rank', 0):+d})\n- Composite: {trend.get('composite', 0):.4f} (delta: {trend.get('delta_composite', 0):+.4f})\n")
    ctx = ContextBuilder(conn, config).build_person_context(person, recent_count=30)
    if ctx.fact_archive:
        archive_sections = _extract_sections(ctx.fact_archive)
        for section_name in ("客户时间线", "月度消息分布", "关键信息"):
            content = archive_sections.get(section_name, "")
            if content:
                if compact and section_name == "客户时间线":
                    entries = re.split(r"(?=^### )", content, flags=re.MULTILINE)
                    entries = [e for e in entries if e.strip()]
                    if len(entries) > 10:
                        content = f"(共 {len(entries)} 条，显示最近 10 条)\n" + "\n".join(entries[-10:])
                parts.append(f"## {section_name}\n{content}\n")
    else:
        wxids_fallback = [a["wxid"] for a in identity["accounts"] if a["wxid"]]
        monthly = _generate_monthly_summary(conn, wxids_fallback, config.my_wxid)
        if monthly:
            parts.append(f"## 月度消息分布（自动生成）\n{monthly}\n")
    # 信号检测
    signals = data["signals"]
    if signals:
        parts.append("## 信号检测\n")
        if "rejection" in signals:
            parts.append("### 拒绝信号")
            for s in signals["rejection"][:5]:
                parts.append(f"- {s}")
            parts.append("")
        if "confession" in signals:
            parts.append("### 确认/签约信号")
            for s in signals["confession"][:5]:
                parts.append(f"- {s}")
            parts.append("")
        if "invitation" in signals:
            parts.append("### 会面信号")
            for s in signals["invitation"][:5]:
                parts.append(f"- {s}")
            parts.append("")
        if "moments_strong_signal" in signals:
            parts.append("### 朋友圈强信号（关注期评论）")
            for s in signals["moments_strong_signal"][:5]:
                parts.append(f"- {s}")
            parts.append("")
        if "moments_weak_signal" in signals:
            parts.append("### 朋友圈弱信号（关注期点赞）")
            for s in signals["moments_weak_signal"][:5]:
                parts.append(f"- {s}")
            parts.append("")
        if "moments_comment" in signals:
            parts.append("### 朋友圈评论")
            for s in signals["moments_comment"][:5]:
                parts.append(f"- {s}")
            parts.append("")
        if "moments_conversation" in signals:
            parts.append("### 朋友圈对话式互动")
            for s in signals["moments_conversation"][:3]:
                parts.append(f"- {s}")
            parts.append("")
        if "moments_one_sided" in signals:
            parts.append("### 朋友圈单向投入")
            for s in signals["moments_one_sided"][:3]:
                parts.append(f"- {s}")
            parts.append("")
        _MANIPULATION_LABELS = {
            "money_requests": "金钱话题（红包/转账/买东西）",
            "sweet_escalation": "称呼过于亲昵（异常亲昵称呼）",
            "victim_play": "示弱卖惨频率异常",
            "amount_escalation": "大额数字/贵重物品提及",
        }
        manipulation_found = False
        for key, label in _MANIPULATION_LABELS.items():
            if key in signals:
                if not manipulation_found:
                    parts.append("### 操控信号预警")
                    manipulation_found = True
                parts.append(f"\n{label}")
                for s in signals[key][:3]:
                    parts.append(f"- {s}")
        if manipulation_found:
            parts.append("\n> 参考 [[情感操控识别]]：以上信号不一定代表操控，但需要警惕。如果多个信号同时出现且投入严重不对等，建议认真评估。")
            parts.append("")
    # 朋友圈
    moments_text = data.get("moments")
    if moments_text:
        parts.append(f"## 朋友圈\n{moments_text}\n")
    # 事件摘要
    events_list = data["events"]
    if events_list:
        parts.append(f"## 事件摘要 ({len(events_list)} 条)\n")
        for e in events_list[:10]:
            parts.append(f"- [{e['date']}] {e['event_type']}: {e['detail']} ({e['confidence']:.0%})")
        parts.append("")
    # 最近聊天
    msgs = data["recent_messages"]
    if msgs:
        if compact:
            msgs = _select_important_messages(msgs, 20)
        parts.append(f"## 最近聊天 ({len(msgs)} 条)\n")
        for msg in msgs:
            ts = datetime.fromtimestamp(msg["timestamp"]).strftime("%m-%d %H:%M")
            max_len = 50 if compact else 80
            content = msg["content"][:max_len]
            if len(msg["content"]) > max_len:
                content += "..."
            sender = msg.get("sender", "未知")
            parts.append(f"- [{ts}] {sender}: {content}")
        parts.append("")
    # Block 2: 历史分析
    parts.append("# 历史分析\n")
    analysis = data.get("latest_analysis")
    slug = slug_display_name(person.display_name)
    analysis_dir = OUTPUTS_ANALYSIS_DIR / f"{slug}__{person.id}"
    analysis_path = analysis_dir / "latest.yaml"
    if analysis:
        stage_info = analysis.get("stage", {})
        if isinstance(stage_info, dict):
            stage_val = stage_info.get("stage", "未知")
            stage_conf = stage_info.get("confidence", 0)
            stage_reasoning = stage_info.get("reasoning", "N/A")
        else:
            stage_val = stage_info
            stage_conf = 0
            stage_reasoning = "N/A"
        parts.append(f"## 最新分析\n- 时间: {analysis.get('generated_at', 'N/A')}\n- 阶段: {stage_val} (置信度: {stage_conf:.0%})\n- 依据: {stage_reasoning[:200]}\n")
        if analysis.get("diagnosis"):
            diag = analysis["diagnosis"]
            parts.append(f"### 诊断\n{diag[:200] if compact else diag[:300]}\n")
        if analysis.get("strategy"):
            strat = analysis["strategy"]
            parts.append(f"### 策略\n{strat[:200] if compact else strat[:400]}\n")
        if analysis.get("risks"):
            parts.append("### 风险")
            for r in analysis["risks"][:3]:
                parts.append(f"- {r}")
            parts.append("")
        history_dir = analysis_dir / "history"
        if history_dir.is_dir():
            history_files = sorted(history_dir.glob("*.yaml"), reverse=True)
            if len(history_files) >= 2:
                parts.append("## 历史变化")
                prev_path = history_files[1]
                try:
                    with open(prev_path, encoding="utf-8") as f:
                        prev = yaml.safe_load(f)
                    prev_stage = prev.get("stage", {})
                    cur_stage = stage_info
                    prev_stage_val = prev_stage.get("stage", "?") if isinstance(prev_stage, dict) else prev_stage
                    cur_stage_val = cur_stage.get("stage", "?") if isinstance(cur_stage, dict) else cur_stage
                    if prev_stage_val != cur_stage_val:
                        parts.append(f"- 阶段变化: {prev_stage_val} → {cur_stage_val}")
                    parts.append(f"- 上次分析: {prev.get('generated_at', 'N/A')} (阶段: {prev_stage_val})")
                except Exception:
                    pass
                parts.append("")
    else:
        parts.append("（无历史分析记录，使用 `agent save` 保存分析结论）\n")
    failures = data.get("similar_failures", [])
    if failures:
        parts.append(f"## 相似失败案例 ({len(failures)} 个)\n")
        for i, f in enumerate(failures[:3], 1):
            if isinstance(f, dict):
                parts.append(f"### 案例 {i}: {f.get('person', '未知')} ({f.get('stage', '未知')})\n- 原因: {f.get('cause', 'N/A')}\n- 教训: {f.get('lesson', 'N/A')}\n")
            else:
                parts.append(f"### 案例 {i}\n- {f}\n")
    patterns = data.get("personal_patterns", [])
    if patterns:
        parts.append("## 个人模式警告\n")
        for w in patterns:
            parts.append(f"- {w}")
        parts.append("")
    # Block 3: 推荐阅读
    parts.append("# 推荐阅读\n")
    wiki_results = data["recommendations"]["wiki"]
    if wiki_results:
        parts.append("## 推荐 Wiki 页面")
        parts.append("> 基于当前数据自动检索的相关知识页面，Agent 可按需 `agent material show` 读取全文\n")
        for r in wiki_results:
            summary_short = r["summary"][:60] + "..." if len(r["summary"]) > 60 else r["summary"]
            parts.append(f"- **{r['title']}** — {summary_short}")
            parts.append(f"  - Show: `wiki_show(\"{r['path']}\")`")
        parts.append("")
    framework_pages = data["recommendations"]["frameworks"]
    if framework_pages:
        parts.append("## 推荐分析框架")
        parts.append("> Agent 分析时应参考的 Wiki 框架页面，用 wiki_show() 读取后套用\n")
        for path, desc in framework_pages:
            parts.append(f"- **{path.split('/')[-1].replace('.md', '')}** — {desc}")
            parts.append(f"  - Show: `wiki_show(\"docs/wiki/{path}\")`")
        parts.append("")
    parts.append("## 建议操作")
    parts.append(f"- `chat(\"{person.display_name}\", recent=200)`")
    parts.append(f"- `evidence(\"{person.display_name}\", section=\"timeline\")`")
    if events_list:
        parts.append(f"- `wiki_search(\"{events_list[0]['event_type']}\")`")
    parts.append(f"- `save_from_markdown(\"{person.display_name}\", analysis_md)`")
    parts.append("")
    parts.append(_build_cross_refs(
        person, has_chat=True, has_fact=ctx.has_archive, has_event=bool(events_list),
        has_analysis=analysis is not None,
        wiki_hits=[r["path"] for r in wiki_results] if wiki_results else None,
    ))
    return "\n".join(parts)


def _build_wiki_queries(signals: dict[str, list[str]], stage: str) -> list[str]:
    """根据检测到的信号和销售阶段，生成推荐的 wiki_context 查询词。

    供 person_brief 返回 recommended_wiki_queries 字段，Agent 可直接传给 wiki_context。
    """
    queries: list[str] = []

    if stage and stage != "未识别":
        queries.append(f"{stage}阶段 策略 推进方法")

    signal_queries = {
        "rejection": "拒绝信号 销售止损 跟进策略",
        "confession": "意向表达 购买信号 逼单策略",
        "invitation": "客户邀约 会面安排 商务会谈",
        "cold": "冷淡 降温 需求感控制 跟进频率",
        "manipulation": "价格谈判 条件试探 客户博弈",
        "moments_strong_ioi": "朋友圈互动 商务展示面 信任建立",
    }
    seen: set[str] = set()
    for sig_type, query in signal_queries.items():
        if sig_type in signals and query not in seen:
            queries.append(query)
            seen.add(query)

    if not queries:
        queries.append("销售三要素 需求确认 信任建立")

    return queries


def _detect_stage_label(conn, config, person) -> str:
    """从阶段识别器获取短标签阶段名（如 潜客/需求确认/方案展示）。"""
    try:
        from engine.analyzers.stage_recognizer import recognize_stage
        result = recognize_stage(conn, config, person)
        return result.current_stage if result else ""
    except Exception:
        return ""


def agent_brief_data(
    conn: sqlite3.Connection, config: Config, person: IdentityPerson,
) -> dict:
    """结构化摘要 — 返回 ToolEnvelope dict，不返回 Markdown。

    第一版必含字段：identity / message_stats / metrics / events / signals /
    recent_messages / latest_analysis / recommendations。
    朋友圈和失败案例为可选字段。
    """
    from engine.agent.context import ContextBuilder
    from engine.analyzers.events import detect_events
    from engine.agent.response import ok
    from engine.agent.signals import _detect_signals, detect_manipulation_signals, _detect_moments_chat_signals, _query_signal_messages
    from engine.agent.moments import _query_moments_data, _format_moments_section
    from engine.agent.recommend import _recommend_wiki, _build_framework_recommendations
    from engine.agent.snapshot import _detect_personal_patterns

    ctx = ContextBuilder(conn, config).build_person_context(person, recent_count=30)
    events = detect_events(conn, person)
    wxids = [a.wxid for a in person.accounts if a.wxid]
    signal_messages = _query_signal_messages(conn, wxids, config.my_wxid, months=3)
    slug = slug_display_name(person.display_name)
    analysis_dir = OUTPUTS_ANALYSIS_DIR / f"{slug}__{person.id}"
    analysis_path = analysis_dir / "latest.yaml"

    # identity
    identity = {
        "person_id": person.id,
        "display_name": person.display_name,
        "accounts": [{"wxid": a.wxid, "conversation_id": a.conversation_id} for a in person.accounts],
    }

    # message_stats
    stats = ctx.message_stats

    # metrics
    metrics = ctx.metrics

    # events
    events_list: list[dict] = []
    for e in events[:10]:
        events_list.append({
            "date": e.date,
            "event_type": e.event_type.value,
            "detail": e.detail,
            "confidence": e.confidence,
        })

    # signals
    signals: dict[str, list[str]] = {}
    if signal_messages:
        signals = _detect_signals(signal_messages)
        manipulation = detect_manipulation_signals(signal_messages, config.my_wxid)
        for k, v in manipulation.items():
            signals.setdefault(k, []).extend(v)
    if person.accounts:
        wxid = person.accounts[0].wxid
        moments_signals = _detect_moments_chat_signals(conn, wxid, config.my_wxid, person.display_name)
        for k, v in moments_signals.items():
            signals.setdefault(k, []).extend(v)

    # recent_messages (already has id/sender_id/is_mine from ContextBuilder)
    recent_messages = ctx.recent_messages[-30:] if len(ctx.recent_messages) > 30 else ctx.recent_messages

    # latest_analysis
    latest_analysis = None
    if analysis_path.is_file():
        try:
            with open(analysis_path, encoding="utf-8") as f:
                latest_analysis = yaml.safe_load(f)
        except Exception:
            pass

    # recommendations
    wiki_results = _recommend_wiki(conn, config, person, ctx, events, max_pages=5)
    relationship_stage = _detect_stage_label(conn, config, person)
    recommended_wiki_queries = _build_wiki_queries(signals, relationship_stage)
    recommendations = {
        "wiki": [
            {"title": r["title"], "path": r["path"], "summary": r["summary"][:60]}
            for r in wiki_results
        ] if wiki_results else [],
        "frameworks": _build_framework_recommendations(signals, ctx.has_archive),
        "recommended_wiki_queries": recommended_wiki_queries,
        "relationship_stage": relationship_stage,
    }

    # optional: 朋友圈
    moments_text = ""
    if person.accounts:
        wxid = person.accounts[0].wxid
        moments_data = _query_moments_data(conn, wxid, config.my_wxid, person.display_name)
        moments_text = _format_moments_section(moments_data)

    # optional: 排名趋势
    ranking_trend = ctx.ranking_trend
    # optional: 数据可信度
    data_confidence = ctx.data_confidence
    # optional: 失败案例
    similar_failures = ctx.similar_failures
    # optional: 个人模式
    patterns = _detect_personal_patterns()

    data = {
        "identity": identity,
        "message_stats": {
            "total": stats.get("total", 0),
            "my_count": stats.get("my_count", 0),
            "customer_count": stats.get("customer_count", 0),
            "first_ts": stats.get("first_ts"),
            "last_ts": stats.get("last_ts"),
            "first_ts_str": _ts_to_beijing(stats.get("first_ts")),
            "last_ts_str": _ts_to_beijing(stats.get("last_ts")),
        },
        "metrics": metrics,
        "events": events_list,
        "signals": signals,
        "recent_messages": recent_messages,
        "latest_analysis": latest_analysis,
        "recommendations": recommendations,
        # 可选字段（后续版本补充为必含）
        "ranking_trend": ranking_trend,
        "data_confidence": data_confidence,
        "similar_failures": similar_failures,
        "personal_patterns": patterns,
        "moments": moments_text or None,
    }

    return ok(data, person_id=person.id, display_name=person.display_name)
