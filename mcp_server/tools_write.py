"""MCP 写入工具函数（无装饰器，由 server.py 注册）。

SalesCRM 版本：客户关系数据写入工具。
术语：会面。
"""

from typing import Optional

from engine.tools import (
    note, date, evaluate as _evaluate, events as _events,
    sync_person as _sync_person, save_analysis as _save_analysis,
    contact, exclude, failure, sticker,
    save_from_markdown as _save_from_markdown,
    sync_moments as _sync_moments,
)


def person_note(name: str, content: str) -> dict:
    """添加客户备注。"""
    try:
        result = note(name, content)
        return {"success": True, "message": result}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查客户姓名是否正确"}


def person_date_record(name: str, date_text: str, location: Optional[str] = None, rating: Optional[int] = None) -> dict:
    """记录会面信息。"""
    try:
        result = date(name, date_text=date_text, location=location, rating=rating)
        return {"success": True, "message": result}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查参数是否正确"}


def person_sync(name: str, mode: str = "incremental") -> dict:
    """增量同步单个客户最新消息。

    什么时候用：分析前确保数据新鲜，增量模式几秒完成不阻塞。
    返回什么：dict 含 success/message 字段，message 是同步结果摘要。
    边界是什么：name 必填；mode 默认 incremental（快），可选 full（慢）。
    需要 WCD 后端运行中，否则返回连接失败提示。
    """
    try:
        result = _sync_person(name, mode=mode)
        return {"success": True, "message": result}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "确保 WCD 后端已启动"}


def person_save_analysis(
    name: str,
    stage: str = "",
    confidence: float = 0.0,
    reasoning: str = "",
    signals: Optional[list[str]] = None,
    next_step: str = "",
    diagnosis: str = "",
    strategy: str = "",
    risks: Optional[list[str]] = None,
    skills_used: Optional[list[str]] = None,
) -> dict:
    """⚠️【覆盖写入】保存分析结论到 data/outputs/analysis/。

    什么时候用：完成客户分析后，将结论持久化以便后续对比和追踪。
    返回什么：dict 含 success/message/path/previous_info/changed_fields/history_path 字段。
    边界是什么：覆盖写入（同人会覆盖上一次的 latest.yaml，旧版本自动转为 previous.yaml，
    同时 history/ 目录保留带时间戳的历史副本）。返回的 previous_info 和 changed_fields
    用于告知调用方被覆盖的旧版本信息及本次变更字段。
    stage/confidence/reasoning 为核心字段，其余可选。
    """
    try:
        result = _save_analysis(
            name,
            stage=stage, confidence=confidence, reasoning=reasoning,
            signals=signals, next_step=next_step,
            diagnosis=diagnosis, strategy=strategy,
            risks=risks, skills_used=skills_used,
        )
        return {
            "success": True,
            "message": f"分析已保存: {result['path']}",
            "path": result["path"],
            "previous_info": result["previous_info"],
            "changed_fields": result["changed_fields"],
            "history_path": result["history_path"],
        }
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查客户姓名和分析参数"}


def person_evaluate(name: str, text: str) -> dict:
    """添加客户评价。

    什么时候用：需要对某客户的关系状态做出评价判断时。
    返回什么：dict 含 success/message 字段。
    边界是什么：追加写入，直接执行。name 和 text 必填。
    """
    try:
        result = _evaluate(name, text)
        return {"success": True, "message": result}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查客户姓名是否正确"}


def events_save(name: str, disconnect_days: int = 7) -> dict:
    """检测并写入关系事件（一步完成检测+写入）。

    什么时候用：需要检测断联、恢复等关系事件并写入事实档案时。
    返回什么：dict 含 success/message 字段，message 为检测结果+写入结果。
    边界是什么：直接调用即自动检测+写入；建议先调 events_scan 展示结果供用户确认，但非强制。
    disconnect_days 控制断联判定阈值（默认 7 天）。
    """
    try:
        result = _events(name, scan=True, disconnect_days=disconnect_days)
        return {"success": True, "message": result, "written": True}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查客户姓名是否正确"}


# ── Phase 2 P2: contact/sticker/exclude/failure 写入 ─────────


def contact_alias(query: str, alias_type: str = "", value: str = "", sensitivity: str = "normal") -> dict:
    """为联系人添加别名。

    什么时候用：需要给联系人添加备注名、外号等别名时。
    返回什么：dict 含 success/message 字段。
    边界是什么：追加写入，直接执行。写错别名无法通过本工具修改，请调 contact_alias_remove 删除后重设。
    """
    try:
        result = contact(query, action="alias", type=alias_type, value=value, sensitivity=sensitivity)
        return {"success": True, "message": result}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查客户姓名是否正确"}


def contact_alias_remove(query: str, alias_type: str, value: str = "") -> dict:
    """删除联系人的别名。

    什么时候用：别名写错或不再需要时删除。
    返回什么：dict 含 success/message/deleted 字段。
    边界是什么：alias_type 必填；value 为空时删除该类型的所有别名，value 非空时只删匹配的那条。
    """
    try:
        result = contact(query, action="remove_alias", type=alias_type, value=value or None)
        deleted = "已删除" in result and "条别名" in result
        return {"success": True, "message": result, "deleted": deleted}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查客户姓名和 alias_type 是否正确"}


def contact_merge(source: str, target: str) -> dict:
    """合并两个联系人（⚠️ 不可逆操作）。

    什么时候用：发现同一个人有两个身份记录需要合并时。
    返回什么：dict 含 success/message 字段。失败时 success=False。
    边界是什么：source 会被合并到 target，操作不可逆！
    同人检查：source == target 时直接返回错误，不执行。
    """
    if source == target:
        return {
            "success": False,
            "error": "SAME_PERSON",
            "message": f"source 和 target 是同一人 ({source})，无需合并",
            "suggestion": "请指定两个不同的联系人",
        }
    try:
        result = contact(source, action="merge", merged=target)
        if "合并失败" in result or "未找到" in result:
            return {
                "success": False,
                "message": result,
                "suggestion": "请检查两个联系人姓名是否正确",
            }
        return {"success": True, "message": result, "warning": "不可逆操作已执行"}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查两个联系人姓名是否正确"}


def sticker_label(md5: str, label: str = "", emotion: str = "", content_type: str = "") -> dict:
    """标注贴纸含义。

    什么时候用：需要为贴纸添加语义标注（情绪、内容类型）时。
    返回什么：dict 含 success/message 字段。
    边界是什么：md5 可以前缀匹配；label/emotion/content_type 为标注内容。
    """
    try:
        result = sticker(action="label", md5=md5, label=label, emotion=emotion, content_type=content_type)
        return {"success": True, "message": result}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查 md5 是否正确"}


def exclude_add(name: str, reason: str = "手动排除") -> dict:
    """将联系人加入手动排除列表。

    什么时候用：需要将某人排除出排名（如已结束的关系）时。
    返回什么：dict 含 success/message 字段。
    边界是什么：name 必填，reason 为排除原因。
    """
    try:
        result = exclude(action="add", name=name, reason=reason)
        return {"success": True, "message": result}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查客户姓名是否正确"}


def exclude_remove(name: str) -> dict:
    """将联系人从手动排除列表移除。

    什么时候用：需要恢复某人参与排名时。
    返回什么：dict 含 success/message 字段。
    边界是什么：name 必填。
    """
    try:
        result = exclude(action="remove", name=name)
        return {"success": True, "message": result}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查客户姓名是否正确"}


def failure_add(
    person: str, stage: str = "", cause: str = "", lesson: str = "",
    signals: str = "", outcome: str = "",
) -> dict:
    """记录失败案例。

    什么时候用：客户关系结束或失败后，记录教训供未来参考。
    返回什么：dict 含 success/message 字段。
    边界是什么：person 必填；signals 为逗号分隔的信号列表。
    """
    try:
        result = failure(
            action="add", person=person, stage=stage, cause=cause,
            lesson=lesson, signals=signals, outcome=outcome,
        )
        return {"success": True, "message": result}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查参数"}


def save_from_markdown_tool(name: str, markdown_text: str) -> dict:
    """从结构化 Markdown 保存分析（覆盖写入）。

    什么时候用：需要从 Markdown 格式的分析文本保存结论时。
    返回什么：dict 含 success/message 字段。
    边界是什么：覆盖写入，与 save_analysis 类似但输入为 Markdown。
    """
    try:
        result = _save_from_markdown(name, markdown_text)
        return {"success": True, "message": f"已保存: {result}"}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查 Markdown 格式和客户姓名"}


def sync_moments_tool(name: str) -> dict:
    """同步朋友圈互动到事实档案。

    什么时候用：需要将朋友圈互动数据同步到客户档案时。
    返回什么：dict 含 success/message 字段。
    边界是什么：追加写入；name 必填。
    """
    try:
        result = _sync_moments(name)
        return {"success": True, "message": result}
    except Exception as e:
        return {"error": "TOOL_ERROR", "message": str(e), "suggestion": "请检查客户姓名是否正确"}
