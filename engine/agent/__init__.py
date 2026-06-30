"""Agent 系统 — 数据工具 + Skill 注册。

LLM 推理由 Agent 自身完成，不再有代码级 pipeline。
所有数据工具统一通过 engine.tools 导入。

保留的模块：
    core.py      — 共享基础设施（连接/解析/交叉引用）
    brief.py     — 全局摘要
    chat.py      — 聊天证据
    evidence.py  — 事实追溯
    material.py  — 材料搜索/阅读
    write.py     — 数据写入
    moments.py   — 朋友圈
    sync_agent.py — 数据同步
    report.py    — 指标报告
    identity_ops.py — 身份管理
    signals.py   — 信号检测
    context.py   — 上下文组装器
    registry.py  — Skill 注册表
"""
