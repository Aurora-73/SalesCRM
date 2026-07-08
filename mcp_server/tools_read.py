"""MCP 只读工具函数（无装饰器，由 server.py 注册）。

SalesCRM 版本：客户关系数据分析工具。
术语：客户/商务关系/会面/意向。
"""

from typing import Optional

from engine.tools import (
    brief_data, chat_data, metrics, rank_data, status_data,
    wiki_search_data, wiki_show, wiki_context_data,
    timeline, signals,
    evidence, compare_analysis, weekly, moments_stats,
    maintain_candidates, format_candidates,
    events, check_keys,
    contact, exclude, failure, sticker,
    message_context_data, save_from_markdown as _save_from_markdown,
    sync_moments as _sync_moments,
)


def person_brief(name: str) -> dict:
    """获取客户简要信息。"""
    try:
        return brief_data(name)
    except Exception as e:
        return {"error": "PERSON_NOT_FOUND", "message": str(e), "suggestion": "请检查客户姓名是否正确，或先使用 sync 同步数据"}


CHAT_MAX_RECENT = 500


def person_chat(
    name: str, recent: int = 30, keyword: Optional[str] = None,
    from_date: Optional[str] = None, to_date: Optional[str] = None,
    context_lines: int = 0,
) -> dict:
    """获取客户聊天记录。

    什么时候用：需要查看与某客户的具体对话内容时。
    返回什么：dict 含 messages 列表，每条消息含 id/sender_id/is_mine/timestamp/content。
    边界是什么：recent 控制返回消息数量（硬上限 500，防止返回超限）；keyword 按关键词过滤（context_lines 仅在 keyword 模式下生效，控制匹配消息的上下文条数）；
    from_date/to_date 按日期范围过滤（格式 YYYY-MM-DD）。
    """
    original_recent = recent
    if recent <= 0 or recent > CHAT_MAX_RECENT:
        recent = CHAT_MAX_RECENT
    try:
        result = chat_data(name, recent=recent, keyword=keyword,
                           from_date=from_date, to_date=to_date,
                           context_lines=context_lines)
        if original_recent <= 0 or original_recent > CHAT_MAX_RECENT:
            if isinstance(result, dict) and "data" in result:
                result["data"]["truncated"] = True
                result["data"]["original_recent"] = original_recent
                result["data"]["applied_recent"] = recent
                result["data"]["truncation_reason"] = f"recent={original_recent} 超出上限 {CHAT_MAX_RECENT}，已自动截断"
        return result
    except Exception as e:
        return {"error": "PERSON_NOT_FOUND", "message": str(e), "suggestion": "请检查客户姓名是否正确"}


def person_metrics(name: str) -> dict:
    """获取客户关系指标。"""
    try:
        result = metrics(name)
        if isinstance(result, str):
            return {"error": "PERSON_NOT_FOUND", "message": result, "suggestion": "请检查客户姓名是否正确"}
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查数据库连接"}


def person_rank() -> dict:
    """获取所有客户的商务热度排名。"""
    try:
        result = rank_data()
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查数据库连接"}


def person_status(name: str) -> dict:
    """获取客户状态概览。"""
    try:
        return status_data(name)
    except Exception as e:
        return {"error": "PERSON_NOT_FOUND", "message": str(e), "suggestion": "请检查客户姓名是否正确"}


def wiki_search(query: str, limit: int = 5) -> dict:
    """搜索 Wiki 知识库（销售知识、技巧、场景应对策略）。"""
    try:
        return wiki_search_data(query, limit=limit)
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查 Wiki 配置"}


def wiki_read(path: str, max_chars: int = 8000) -> dict:
    """读取 Wiki 页面完整正文。

    什么时候用：wiki_search 找到感兴趣的知识点后，需要阅读完整内容时。
    返回什么：dict 含 path/content/total_chars/truncated 字段。
    边界是什么：path 是 wiki_search 返回的 path 字段；max_chars 控制返回长度，超过则截断。
    """
    try:
        content = wiki_show(path, max_chars=max_chars)
        return {"path": path, "content": content, "max_chars": max_chars}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查 path 是否正确，应使用 wiki_search 返回的 path"}


def wiki_context(
    queries: list[str],
    task_type: str = "analyze",
    stage: str = "",
    focus: str = "",
    max_chars: int = 8000,
    max_pages: int = 8,
) -> dict:
    """批量构建 Wiki 知识上下文（推荐作为主入口，替代多次 wiki_search+wiki_read）。

    什么时候用：
    - 分析客户时，拿到 brief 的阶段/信号后，一次性构建知识图景
    - 看到聊天模式后，需要查策略和话术时
    - 写报告前，需要回顾相关 Wiki 条目时

    与 wiki_search 的区别：
    - wiki_context 合并多条查询 + 阶段过滤 + 焦点加权，一次返回格式化 prompt 段落
    - wiki_search 返回候选列表，需要逐条 wiki_read 读全文
    wiki_search/wiki_read 保留用于精确钻取单页内容。

    返回什么：dict 含 prompt_section（可直接嵌入推理的 Markdown 段落）、
    meta（hit_pages/returned_pages/deduped/total_chars/low_confidence）、
    page_list（命中页面摘要，供需要时用 wiki_read 钻取）。

    边界：queries 最多 5 条（超出自动截断）；stage 从 person_brief 的 relationship_stage
    获取；focus 取 signals/strategy/risk/date/chat。
    """
    try:
        return wiki_context_data(
            queries=queries,
            task_type=task_type,
            stage=stage,
            focus=focus,
            max_chars=max_chars,
            max_pages=max_pages,
        )
    except Exception as e:
        return {
            "error": "TOOL_ERROR",
            "message": str(e),
            "suggestion": "请检查 queries 格式（应为字符串列表）和参数值",
        }


# ── Phase 2 P1: 只读工具 ──────────────────────────────────────


def person_timeline(name: str, max_events: int = 30) -> dict:
    """获取客户关系时间线。

    什么时候用：需要查看客户关系发展的关键事件时间线时。
    返回什么：dict 含 person_id/display_name/events 列表。
    边界是什么：max_events 控制返回事件数量。
    """
    try:
        return timeline(name, max_events=max_events)
    except Exception as e:
        return {"error": "PERSON_NOT_FOUND", "message": str(e), "suggestion": "请检查客户姓名是否正确"}


def person_signals(name: str) -> dict:
    """获取信号详情（基础信号 + 操控信号 + 朋友圈联动信号）。

    什么时候用：需要深入了解检测到的各类信号时。
    返回什么：dict 含 person_id/display_name/basic_signals/manipulation_signals/moments_signals。
    边界是什么：name 必填。
    """
    try:
        return signals(name)
    except Exception as e:
        return {"error": "PERSON_NOT_FOUND", "message": str(e), "suggestion": "请检查客户姓名是否正确"}


def person_evidence(name: str, section: str = "all", since_date: Optional[str] = None) -> dict:
    """获取事实档案（timeline/evaluations/notes/dates/all）。

    什么时候用：需要查看已记录的客观事实（笔记、评价、会面记录等）时。
    返回什么：dict 含 name/section/content/has_analysis 字段，content 为 Markdown 格式。
    边界是什么：section 可选 all/timeline/evaluations/notes/dates；since_date 过滤起始日期。
    分析内容不在事实档案中，请使用 person_save_analysis/person_compare 查看分析结论。
    """
    try:
        result = evidence(name, section=section, since_date=since_date)
        from pathlib import Path
        from engine.config import ROOT_DIR
        analysis_dir = ROOT_DIR / "data" / "outputs" / "analysis"
        has_analysis = any(analysis_dir.glob(f"{name}*")) if analysis_dir.is_dir() else False
        hint = ""
        if not has_analysis:
            hint = "\n\n---\n**提示**: 未找到分析记录。分析内容存储在 data/outputs/analysis/，请使用 person_save_analysis 保存分析，或 person_compare 对比历史分析。"
        else:
            hint = "\n\n---\n**提示**: 检测到已有分析记录。请使用 person_compare 查看分析对比，或 person_save_analysis 更新分析。"
        return {
            "name": name,
            "section": section,
            "content": result + hint,
            "has_analysis": has_analysis,
        }
    except Exception as e:
        return {"error": "PERSON_NOT_FOUND", "message": str(e), "suggestion": "请检查客户姓名是否正确"}


def person_compare(name: str) -> dict:
    """对比 latest.yaml 和 previous.yaml 的变化趋势。

    什么时候用：需要了解一个客户与上次分析相比的变化时。
    返回什么：dict 含 name/content 字段，content 为对比分析 Markdown。
    边界是什么：需要至少两次 save_analysis 才有对比数据。
    """
    try:
        result = compare_analysis(name)
        return {"name": name, "content": result}
    except Exception as e:
        return {"error": "PERSON_NOT_FOUND", "message": str(e), "suggestion": "请检查客户姓名是否正确"}


def weekly_report(deep: bool = False) -> dict:
    """生成周报。

    什么时候用：需要生成本周客户维护总结报告时。
    返回什么：dict 含 content 字段，content 为周报 Markdown。
    边界是什么：deep=True 时生成深度报告（更耗时）。
    """
    try:
        result = weekly(deep=deep)
        return {"content": result, "deep": deep}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查数据库连接"}


def person_moments_stats(name: str) -> dict:
    """获取朋友圈互动统计。

    什么时候用：需要分析朋友圈互动频率和模式时。
    返回什么：dict 含朋友圈互动统计数据。
    边界是什么：name 必填。
    """
    try:
        result = moments_stats(name)
        if isinstance(result, str):
            return {"error": "PERSON_NOT_FOUND", "message": result, "suggestion": "请检查客户姓名是否正确"}
        return result
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查客户姓名是否正确"}


_REASON_PRIORITY = {
    "兴趣下降": "高",
    "意向未推进": "高",
    "高潜力未投入": "中",
    "需关注": "低",
}

_REASON_ACTION = {
    "兴趣下降": "重新建立联系，分享行业资讯，避免关系冷却",
    "意向未推进": "推进关系，发起约见或方案展示，抓住意向期",
    "高潜力未投入": "主动联系，投入更多关注，测试对方反应",
    "需关注": "保持联系，观察信号变化，避免过度投入",
}


def maintain_list(limit: int = 10) -> dict:
    """获取需要维持关系的候选人列表。

    什么时候用：每周主动维护客户关系时，筛选需要联系的人。
    返回什么：dict 含 candidates 列表和 formatted Markdown。
    边界是什么：limit 控制返回候选人数。
    """
    try:
        candidates = maintain_candidates(max_people=limit)
        if isinstance(candidates, str):
            return {"error": "TOOL_ERROR", "message": candidates, "suggestion": "请检查数据库连接"}
        formatted = format_candidates(candidates)
        return {
            "candidates": [
                {
                    "name": c.name,
                    "rank": c.rank,
                    "priority": _REASON_PRIORITY.get(c.reason, "低"),
                    "reason": c.reason,
                    "signal_level": c.signal_level,
                    "recent_days": c.recent_days,
                    "composite": c.composite,
                    "trend": c.trend,
                    "interaction_pattern": c.interaction_pattern,
                    "last_msg_summary": c.last_msg_summary,
                    "suggested_action": _REASON_ACTION.get(c.reason, "保持联系，观察信号变化"),
                }
                for c in candidates
            ],
            "formatted": formatted,
        }
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查数据库连接"}


# ── Phase 2 P1: events 拆分 ───────────────────────────────────


def events_scan(name: str, disconnect_days: int = 7) -> dict:
    """扫描关系事件（只读，不写入）。

    什么时候用：需要检测断联、恢复、频率变化等关系事件时。
    返回什么：dict 含 name/content 字段，content 为检测结果 Markdown。
    边界是什么：scan=False 只展示不写入；disconnect_days 控制断联判定阈值。
    """
    try:
        result = events(name, scan=False, disconnect_days=disconnect_days)
        return {"name": name, "content": result, "written": False}
    except Exception as e:
        return {"error": "PERSON_NOT_FOUND", "message": str(e), "suggestion": "请检查客户姓名是否正确"}


# ── Phase 2 P1: system_sync + wcd_status ─────────────────────


def system_sync(mode: str = "incremental", meta_only: bool = False) -> dict:
    """全量/增量数据同步。

    什么时候用：需要同步所有客户的微信数据时。⚠️ 可能耗时 1-5 分钟。
    返回什么：dict 含 success/message 字段。
    边界是什么：mode 默认 incremental（快），full 全量（慢）；meta_only 只同步联系人元数据。
    需要 WCD 后端运行中。
    """
    from engine.tools import sync as _sync
    try:
        result = _sync(mode=mode, meta_only=meta_only)
        return {"success": True, "message": result, "mode": mode}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "确保 WCD 后端已启动"}


def wcd_status() -> dict:
    """检查 WCD 后端在线状态 + 密钥缓存状态，给出操作建议。

    什么时候用：同步前确认 WCD 后端是否在线、密钥是否可用。
    返回什么：dict 含 online/keys_cached/message/suggestion 字段。
    边界是什么：只读检查，不启动进程、不获取密钥、不修改任何状态。
    密钥安全：绝不自动调用 fetch_keys（封号风险），密钥失效时仅提示用户手动处理。
    """
    try:
        from engine.importers.wcd_client import WCDClient
        from engine.agent.core import _get_conn
        conn, config = _get_conn()
        try:
            if config.weflow.backend != "wcd":
                return {
                    "online": False,
                    "backend": config.weflow.backend,
                    "message": f"当前后端是 {config.weflow.backend}，非 WCD",
                    "suggestion": "无需 WCD 检查",
                }
            client = WCDClient(
                base_url=config.weflow.base_url,
                decrypted_db_dir=config.weflow.decrypted_db_dir or None,
            )
            online = client.health()
            keys = client.check_cached_keys()
            keys_cached = keys.get("cached", False)

            if online and keys_cached:
                return {
                    "online": True,
                    "keys_cached": True,
                    "message": "WCD 后端在线，密钥已缓存，可以正常同步",
                    "suggestion": None,
                }
            if online and not keys_cached:
                return {
                    "online": True,
                    "keys_cached": False,
                    "message": "WCD 后端在线，但密钥未缓存",
                    "suggestion": "请手动获取密钥并保存到 account_keys.json（注意封号风险，勿频繁获取）",
                }
            if not online and keys_cached:
                return {
                    "online": False,
                    "keys_cached": True,
                    "message": "WCD 后端未启动，但密钥已缓存",
                    "suggestion": "请手动启动 WCD 后端（密钥会自动加载），启动后即可同步",
                }
            return {
                "online": False,
                "keys_cached": False,
                "message": "WCD 后端未启动，密钥也未缓存",
                "suggestion": "请先手动获取密钥保存到 account_keys.json（注意封号风险），再启动 WCD 后端",
            }
        finally:
            conn.close()
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查 WCD 配置"}


def wcd_start(timeout: int = 90) -> dict:
    """启动 WCD 后端进程并等待健康检查通过。

    什么时候用：wcd_status 显示 offline 时调此工具启动后端。
    返回什么：dict 含 success/message/already_running/pid 字段。
    边界是什么：如果 WCD 已在运行，直接返回成功。启动是异步的，进程会持续运行。
    默认 timeout=90s（WCD 后端冷启动通常需要 40-60s，留足余量）。
    密钥安全：不获取密钥，只启动进程。密钥缓存会自动加载。
    """
    import sys
    import time
    import subprocess
    from pathlib import Path

    try:
        from engine.importers.wcd_client import WCDClient
        from engine.agent.core import _get_conn
        conn, config = _get_conn()
        try:
            if config.weflow.backend != "wcd":
                return {
                    "success": False,
                    "message": f"当前后端是 {config.weflow.backend}，非 WCD，无需启动",
                }

            client = WCDClient(
                base_url=config.weflow.base_url,
                decrypted_db_dir=config.weflow.decrypted_db_dir or None,
            )

            # 1. 已在运行则直接返回
            if client.health():
                return {
                    "success": True,
                    "already_running": True,
                    "message": "WCD 后端已在运行，无需重复启动",
                }

            # 2. 定位 WCD 目录（项目本地或共享路径）
            project_root = Path(__file__).resolve().parent.parent
            wcd_dir = project_root / "_reference" / "WeChatDataAnalysis"
            if not wcd_dir.exists():
                # 尝试 loveMentor 共享路径
                alt_dir = Path("E:/Code/loveMentor/_reference/WeChatDataAnalysis")
                if alt_dir.exists():
                    wcd_dir = alt_dir
                else:
                    return {
                        "success": False,
                        "message": f"WCD 目录不存在: {wcd_dir}",
                        "suggestion": "请确认 WCD 后端代码已安装，或从其他项目启动 WCD 后端",
                    }

            # 3. 启动进程（隐藏窗口）
            startupinfo = None
            creationflags = 0
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW

            proc = subprocess.Popen(
                ["uv", "run", "main.py"],
                cwd=str(wcd_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )

            # 4. 轮询健康检查
            start_time = time.time()
            while time.time() - start_time < timeout:
                time.sleep(2)
                if client.health():
                    elapsed = time.time() - start_time
                    return {
                        "success": True,
                        "already_running": False,
                        "pid": proc.pid,
                        "message": f"WCD 后端启动成功（PID: {proc.pid}，耗时 {elapsed:.1f}s）",
                    }
                if proc.poll() is not None:
                    return {
                        "success": False,
                        "pid": proc.pid,
                        "message": f"WCD 后端进程已退出（返回码: {proc.returncode}）",
                        "suggestion": "请手动在 WCD 目录运行 uv run main.py 查看错误信息",
                    }

            process_alive = proc.poll() is None
            return {
                "success": False,
                "pid": proc.pid,
                "process_alive": process_alive,
                "message": f"WCD 后端启动超时（{timeout}s），进程{'仍在运行' if process_alive else '已退出'}",
                "suggestion": "进程仍在运行则健康检查未就绪，可调 wcd_status 复查；进程已退出则需手动在 WCD 目录运行 uv run main.py 查看错误",
            }
        finally:
            conn.close()
    except FileNotFoundError:
        return {
            "success": False,
            "message": "未找到 uv 命令",
            "suggestion": "请确认 uv 已安装并在 PATH 中（pip install uv 或参考 https://docs.astral.sh/uv/）",
        }
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查 WCD 配置和依赖"}


def weflow_status() -> dict:
    """检查 WeFlow 后端在线状态。

    什么时候用：同步前确认 WeFlow 是否已启动。
    返回什么：dict 含 online/message/suggestion 字段。
    边界是什么：只读检查，不启动进程。
    """
    try:
        from engine.importers.weflow_client import WeFlowClient
        from engine.agent.core import _get_conn
        conn, config = _get_conn()
        try:
            if config.weflow.backend != "weflow":
                return {
                    "online": False,
                    "backend": config.weflow.backend,
                    "message": f"当前后端是 {config.weflow.backend}，非 WeFlow",
                    "suggestion": "无需 WeFlow 检查",
                }
            client = WeFlowClient(
                base_url=config.weflow.base_url,
                token=config.weflow.token,
                timeout=5,
            )
            online = client.health()
            if online:
                return {
                    "online": True,
                    "message": "WeFlow 后端在线，可以正常同步",
                    "suggestion": None,
                }
            return {
                "online": False,
                "message": "WeFlow 后端未响应",
                "suggestion": "请手动启动 WeFlow（D:\\WeFlow\\WeFlow.exe），或用 weflow_start 工具",
            }
        finally:
            conn.close()
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查 WeFlow 配置"}


def weflow_start(timeout: int = 60) -> dict:
    """启动 WeFlow 后端进程并等待健康检查通过。

    什么时候用：weflow_status 显示 offline 时调此工具启动 WeFlow。
    返回什么：dict 含 success/message/already_running 字段。
    边界是什么：如果 WeFlow 已在运行，直接返回成功。启动后进程持续运行。
    """
    import subprocess
    import time
    from pathlib import Path

    try:
        from engine.importers.weflow_client import WeFlowClient
        from engine.agent.core import _get_conn
        conn, config = _get_conn()
        try:
            if config.weflow.backend != "weflow":
                return {
                    "success": False,
                    "message": f"当前后端是 {config.weflow.backend}，非 WeFlow，无需启动",
                }

            client = WeFlowClient(
                base_url=config.weflow.base_url,
                token=config.weflow.token,
                timeout=5,
            )

            # 1. 已在运行则直接返回
            if client.health():
                return {
                    "success": True,
                    "already_running": True,
                    "message": "WeFlow 后端已在运行，无需重复启动",
                }

            # 2. 定位 WeFlow.exe
            weflow_exe = Path("D:/WeFlow/WeFlow.exe")
            if not weflow_exe.exists():
                return {
                    "success": False,
                    "message": f"WeFlow 不存在: {weflow_exe}",
                    "suggestion": "请确认 WeFlow 已安装到 D:\\WeFlow\\",
                }

            # 3. 启动进程
            proc = subprocess.Popen(
                [str(weflow_exe)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # 4. 轮询健康检查
            start_time = time.time()
            while time.time() - start_time < timeout:
                time.sleep(2)
                if client.health():
                    elapsed = time.time() - start_time
                    return {
                        "success": True,
                        "already_running": False,
                        "message": f"WeFlow 后端启动成功（耗时 {elapsed:.1f}s）",
                    }
                if proc.poll() is not None:
                    return {
                        "success": False,
                        "message": f"WeFlow 进程已退出（返回码: {proc.returncode}）",
                        "suggestion": "请手动运行 D:\\WeFlow\\WeFlow.exe 查看错误信息",
                    }

            process_alive = proc.poll() is None
            return {
                "success": False,
                "process_alive": process_alive,
                "message": f"WeFlow 启动超时（{timeout}s），进程{'仍在运行' if process_alive else '已退出'}",
                "suggestion": "进程仍在运行则 WeFlow 可能还在加载，可调 weflow_status 复查",
            }
        finally:
            conn.close()
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查 WeFlow 配置"}


# ── Phase 2 P2: contact/sticker/exclude/failure 拆分 ─────────


def contact_search(query: str) -> dict:
    """搜索联系人信息。

    什么时候用：需要查找联系人、查看身份目录信息时。
    返回什么：dict 含 query/content 字段，content 为联系人信息 Markdown。
    边界是什么：query 支持姓名、别名、wxid 多种方式。
    """
    try:
        result = contact(query, action="search")
        return {"query": query, "content": result}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查查询参数"}


def sticker_scan(private_only: bool = True) -> dict:
    """扫描聊天中的贴纸表情（⚠️ 可能耗时）。

    什么时候用：需要建立贴纸词典、分析贴纸使用模式前先扫描。
    返回什么：dict 含 content 字段，content 为扫描结果摘要。
    边界是什么：private_only=True 只扫描私聊。
    """
    try:
        result = sticker(action="scan", private_only=private_only)
        return {"content": result, "private_only": private_only}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查数据库连接"}


def sticker_list(limit: int = 30, unlabeled: bool = False, min_freq: int = 1) -> dict:
    """列出贴纸词典。

    什么时候用：需要查看已扫描的贴纸列表和标注时。
    返回什么：dict 含 content 字段，content 为贴纸列表 Markdown。
    边界是什么：unlabeled=True 只看未标注的；min_freq 过滤最低频率。
    """
    try:
        result = sticker(action="list", limit=limit, unlabeled=unlabeled, min_freq=min_freq)
        return {"content": result, "limit": limit, "unlabeled": unlabeled}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请先运行 sticker_scan"}


def exclude_list() -> dict:
    """查看排除列表（硬排除 + 标签排除 + 手动排除）。

    什么时候用：需要了解哪些联系人被排除出排名及原因时。
    返回什么：dict 含 content 字段，content 为排除列表 Markdown。
    边界是什么：只读，不修改排除状态。
    """
    try:
        result = exclude(action="list")
        return {"content": result}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查数据库连接"}


def failure_list() -> dict:
    """查看所有失败案例。

    什么时候用：需要回顾历史失败教训、避免重蹈覆辙时。
    返回什么：dict 含 content 字段，content 为失败案例列表 Markdown。
    边界是什么：只读。
    """
    try:
        result = failure(action="list")
        return {"content": result}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查数据文件"}


# ── Phase 2 P2: message_context ──────────────────────────────


def message_context(message_ids: list[str], before: int = 20, after: int = 20) -> dict:
    """根据消息 ID 获取前后上下文消息。

    什么时候用：需要查看某条消息的上下文（前后对话）时。
    返回什么：dict 含 messages 列表及元信息。
    边界是什么：message_ids 是消息 ID 列表；before/after 控制上下文条数；不跨会话。
    """
    try:
        return message_context_data(message_ids, before=before, after=after)
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查 message_ids 参数"}
