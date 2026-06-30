# Agent 层

## 概述

`engine/agent/` 是工具函数的实现层。`tools.py` 是包装层（自动解析人名 → conn/config/person），各模块文件包含实际逻辑。

## 核心文件

| 文件 | 功能 |
|------|------|
| `core.py` | 共享基础设施：`_get_conn`、`_resolve_person`、`_build_cross_refs`、`_extract_sections` 等 |
| `context.py` | `ContextBuilder` — 从数据库和文件系统组装客户上下文 |
| `registry.py` | `SkillRegistry` — 解析 skill 文件目录，提供搜索索引 |

## 按域拆分

| 文件 | 包含函数 | 职责 |
|------|---------|------|
| `brief.py` | `agent_brief` | 全局摘要视图（主函数） |
| `snapshot.py` | `_detect_personal_patterns`, `_select_important_messages`, `_generate_monthly_summary` | 摘要辅助（个人模式/消息筛选/月度统计） |
| `recommend.py` | `_recommend_wiki`, `_build_framework_recommendations` | Wiki/框架推荐 |
| `chat.py` | `agent_chat` | 聊天记录查询 |
| `evidence.py` | `agent_evidence` | 事实档案视图 |
| `material.py` | `agent_material_search`, `agent_material_show` | 材料搜索与阅读 |
| `write.py` | `agent_note`, `agent_date`, `agent_evaluate`, `agent_events`, `agent_save_analysis`, `agent_save_from_markdown` | 数据写入 |
| `moments.py` | `moments_stats`, `sync_moments_to_archive` | 朋友圈互动 |
| `sync_agent.py` | `agent_sync`, `sync_person` | 数据同步 |
| `report.py` | `agent_metrics`, `agent_status`, `agent_rank`, `agent_weekly` | 指标与报告 |
| `identity_ops.py` | `agent_contact`, `agent_exclude`, `agent_failure`, `agent_sticker` | 身份与排除管理 |
| `signals.py` | `_detect_signals`, `detect_manipulation_signals`, `_detect_moments_chat_signals`, `_query_signal_messages` | 信号检测（含销售信号） |

## 数据流

```
tools.py (包装层)
    ↓ name → (conn, config, person)
    ├→ brief.py / chat.py / evidence.py / material.py
    ├→ write.py / moments.py / sync_agent.py / report.py / identity_ops.py
    ├→ signals.py (信号检测)
    ├→ core.py (共享基础设施 + Session 连接复用)
    ├→ context.py (上下文组装)
    └→ registry.py (Skill 注册表)
```

底层依赖：
```
engine/analyzers/   指标计算、排名、事件
engine/knowledge/   Wiki 检索
engine/facts/       事实档案读写
engine/identity/    身份解析
engine/models/      数据结构
```

## agent_chat 的 sender 标注逻辑

```python
# chat.py → agent_chat
sender = row["sender_id"] or ""
is_mine = sender == config.my_wxid
"sender": "我" if is_mine else person.display_name,
```

判定依据是 `sender_id == config.my_wxid`。如果 `my_wxid` 配置错误，所有标注都会反转。

### agent_brief 输出结构

`brief()` 返回的 Markdown 包含：
1. **事实快照**：身份、数据可信度、首末条消息时间
2. **指标**：composite 分数、意向等级、子指标表格
3. **事件**：断联/恢复/频率变化检测结果
4. **信号**：拒绝/需求确认/报价/决策人/操控关键词检测
5. **Wiki 推荐**：根据信号自动推荐相关 Wiki 页面
6. **历史分析**：如果有保存过的分析结论

## 注意事项

1. **连接管理**：`_get_conn()` 每次打开新连接，用完必须 `conn.close()`。`tools.py` 的包装层用 `try/finally` 保证关闭。支持 `Session` 上下文管理器复用连接。
2. **person 解析失败**：`_resolve_person` 找不到人时返回 `None`，`tools.py` 包装层会抛 `ValueError("未找到联系人: XX")`。
3. **agent_chat 的 conversation_id**：通过 `person.accounts[0].conversation_id` 获取，如果一个客户有多个微信账号，只用第一个。
4. **信号检测**：`agent_chat` 和 `agent_brief` 会扫描关键词检测拒绝/需求确认/报价/决策人/操控信号，这些是硬编码的关键词列表，不经过 LLM。