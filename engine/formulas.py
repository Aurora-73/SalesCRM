"""公式工具 — 客户战态分析。

从聊天分析的算法模块提取的核心公式，改为 Agent 可调用的工具。
部分参数从 SQLite 自动计算，部分需要 Agent 根据聊天内容判断。

本文件为兼容入口，实际实现已拆分：
- engine.formulas_love — 通用战态公式（IVI/SPE/EWS 等）
- engine.formulas_sales — 销售决策公式（BQ/BSP/BWS 等）

用法：
    from engine.tools import formula_params, formula_ivi, formula_spe, formula_ews, formula_action

    # 第一步：获取所有可自动计算的参数
    params = formula_params("张三")

    # 第二步：Agent 根据聊天内容补全 manual 参数（Pface/Ddepth 等）
    # 第三步：代入公式计算
    ivi = formula_ivi(sp=0.7, fback=0.8, user_investment=0.3, pface=0.4)
    spe = formula_spe(user_ddepth=0.6, target_ddepth=0.5, target_latency=1.2, user_latency=0.8)
    ews = formula_ews(gap_effect=0.3, cp_index=0.5, eev=0.4, scarcity_loss=0.1)
    action = formula_action(ivi=ivi["ivi"], spe=spe["spe"], ews=ews["ews"])
"""

from __future__ import annotations


def _validate_params(**kwargs) -> str | None:
    """校验公式参数类型。返回错误消息或 None。"""
    for name, val in kwargs.items():
        if not isinstance(val, (int, float)):
            return f"{name} 必须是数字，收到 {type(val).__name__}"
    return None


# ── 通用战态公式（从 formulas_love 导入）─────────────────────────────────

from engine.formulas_love import (  # noqa: E402
    formula_params,
    formula_ivi,
    formula_spe,
    formula_ews,
    formula_is,
    formula_gap_effect,
    formula_eev,
    formula_cs,
    formula_action,
)

# ── 销售决策公式（从 formulas_sales 导入）────────────────────────────────

from engine.formulas_sales import (  # noqa: E402
    sales_params,
    sales_bq,
    sales_bsp,
    sales_bws,
    sales_pv,
    sales_action,
)

__all__ = [
    # 共享工具
    "_validate_params",
    # 通用战态公式
    "formula_params",
    "formula_ivi",
    "formula_spe",
    "formula_ews",
    "formula_is",
    "formula_gap_effect",
    "formula_eev",
    "formula_cs",
    "formula_action",
    # 销售决策公式
    "sales_params",
    "sales_bq",
    "sales_bsp",
    "sales_bws",
    "sales_pv",
    "sales_action",
]
