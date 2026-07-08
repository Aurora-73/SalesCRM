# MCP guide 工具改进完成记录

> 完成日期：2026-07-02
> 状态：✅ 已完成并验收通过
> 目标：让纯 MCP 使用者（Claude Desktop / Cursor / Windsurf）无需阅读外部文档，仅通过 MCP 工具本身就能正确、完整地使用系统

---

## 一、改进背景

改进前的 MCP 系统是"零件箱，没有组装说明"——53 个工具完整覆盖功能，但 Agent 不知道：
- 工具调用顺序和依赖关系
- 推理方法论（Wiki 主轴、公式辅助）
- 输出物规范（两文件保存、报告模板）
- 冲突裁决规则
- 操作权限分级

详细的信息差分析见 [mcp_information_gap.md](file:///E:/Code/SalesCRM/readme/mcp_information_gap.md)。

## 二、设计原则

| # | 原则 | 含义 |
|---|------|------|
| 1 | **非侵入** | 不改现有 53 个工具的参数、返回格式、内部逻辑。只新增工具和增强描述 |
| 2 | **按需查** | 流程知识不塞进每个工具描述，而是集中在 guide 工具里，Agent 需要时才查 |
| 3 | **精确指导** | guide 返回的是"下一步该做什么"，不是几百页的完整文档 |
| 4 | **流程可见** | 关键工具的描述中明确指出前/后置依赖（"分析前必须先调 person_sync"） |
| 5 | **同步一致** | 与姊妹项目保持架构一致，通过 exchange/ 机制同步改进 |
| 6 | **单一真相源** | guide 内容是 readme + skills 文档的精简映射，后者是权威来源 |

## 三、改进内容

### 3.1 新增 guide 工具（11 个主题）

| 主题 | 用途 |
|------|------|
| `getting-started` | 快速入门（三件事 + 三场景） |
| `workflow/analysis` | 客户分析完整流程（6步：同步→brief→Wiki→数据→公式→保存） |
| `report-template` | 8 段式分析报告模板 |
| `methodology` | 核心方法论（Wiki 主轴 + 公式辅助 + 冲突裁决 5 级优先级） |
| `rules/evidence` | 事实档案写入规则（自检三问 + 概念分层） |
| `rules/permissions` | 操作权限规范（只读/追加/覆盖/不可逆 4 级） |
| `rules/reply` | 回复构造规则（话术 + 时间线 + 对话领导） |
| `workflow/maintain` | 客户维护工作流（候选人筛选 + 消息输出） |
| `reference/sync` | 同步策略速查（3 种场景 + 范围限制） |
| `reference/formula` | 公式使用指南（两套公式系统 + 阈值 + 核验示例） |
| `reference/stickers` | 贴纸系统（镜像检测 + 标注体系） |

支持中英文别名映射（如"分析"→workflow/analysis，"report"→report-template）。

### 3.2 工具描述增强（23 个工具）

#### P0 关键工具（3 个）

| 工具 | 增强内容 |
|------|---------|
| `person_sync` | 添加 "⚠️【分析前置·必须调用】" |
| `save_from_markdown` | 添加 "⚠️【分析完成·必须调用】" |
| `events_save` | 添加 "⚠️【先扫后写】" |

#### P1 进阶工具（5 个）

| 工具 | 增强内容 |
|------|---------|
| `person_brief` | 添加 "⚠️调此工具前必须先调 person_sync" |
| `person_save_analysis` | 添加 "【可选】" + evidence_refs 参数说明 |
| `maintain_list` | 添加 "详细流程见 guide('workflow/maintain')" |
| `person_evaluate` | 添加 "⚠️概念上属于分析归档，优先级低于客观事实" |
| `contact_merge` | 添加 "⚠️【必须确认】" |

#### 战态分析公式（9 个）

| 工具 | 增强内容 |
|------|---------|
| `formula_get_params` | 添加 "先调此工具获取自动参数" |
| `formula_calc_ivi` ~ `formula_calc_action`（8个） | 添加 "【辅助参考·核验而非套用】" |

#### 销售决策公式（6 个，SalesCRM 独有）

| 工具 | 增强内容 |
|------|---------|
| `sales_get_params` | 添加 "先调此工具获取自动参数" |
| `sales_calc_bq` ~ `sales_calc_action`（5个） | 添加 "【辅助参考·核验而非套用】" |

## 四、上下文预算评估

| 指标 | 改进前 | 改进后 |
|------|--------|--------|
| 工具数量 | 53 | 54（+1 guide） |
| 工具描述总 token | ~1400（估算） | ~2400（估算） |
| 增量 | — | ~+1000 tokens |

**结论**：+1000 tokens 对 Agent 上下文（通常 100K-200K 窗口）影响在 1% 以内，可接受。增量略高于姊妹项目（+800）是因为 SalesCRM 多 6 个销售公式工具的描述增强。

## 五、内容维护机制

### 触发更新条件

| # | 触发场景 | 需要更新的 guide 主题 |
|---|---------|---------------------|
| 1 | 新增 MCP 工具 | getting-started、workflow/analysis |
| 2 | 新增 Wiki 页面 | workflow/analysis（常用 Wiki 表） |
| 3 | 修改操作流程 | workflow/analysis、reference/sync |
| 4 | 修改输出规范 | report-template |
| 5 | 新增权限规则 | rules/permissions |
| 6 | 新增销售公式 | reference/formula |

### 单一真相源关系

```
readme/*.md 和 .claude/skills/*.md  →  权威来源
                   ↓
         tools_guide.py 的 GUIDES  →  精简映射
                   ↓
         Agent 通过 guide(topic) 获取  →  按需查询
```

### 修改代码后自检清单

```
□ 这个改动是否影响现有 guide 主题的内容？
□ 如果是，更新了对应 guide 主题了吗？
□ 更新后调 guide(topic) 验证内容正确吗？
□ guide 内容是否包含恋爱场景相关表述？（应为否）
```

## 六、验收结果

| 验收项 | 结果 |
|--------|------|
| 工具总数 | 54（53+1 guide）✅ |
| guide 11 主题可调用 | ✅ |
| 中文别名映射 | ✅ |
| 未知主题返回列表 | ✅ |
| 无恋爱/约会/表白/暧昧 表述 | ✅ |
| 销售公式 BQ/BSP/BWS/PV 在 guide 中 | ✅ |
| P0 描述增强（3个工具） | ✅ |
| P1 描述增强（5个工具） | ✅ |
| 战态公式描述增强（9个） | ✅ |
| 销售公式描述增强（6个） | ✅ |
| 主项目测试 | 236/236 通过 ✅ |
| MCP 测试 | 10/10 通过 ✅ |
| readme/mcp.md 同步 | ✅ |

## 七、修改文件清单

| 文件 | 操作 |
|------|------|
| [tools_guide.py](file:///E:/Code/SalesCRM/mcp_server/tools_guide.py) | 新建：11 主题 + 别名映射（销售场景适配） |
| [server.py](file:///E:/Code/SalesCRM/mcp_server/server.py) | 修改：注册 guide + 23 个描述增强 |
| [test_final.py](file:///E:/Code/SalesCRM/mcp_server/tests/test_final.py) | 修改：53→54 + test_guide_tool（含恋爱表述检查） |
| [readme/mcp.md](file:///E:/Code/SalesCRM/readme/mcp.md) | 修改：工具数、目录、清单同步 |

## 八、与姊妹项目的差异

| 维度 | 姊妹项目 | SalesCRM |
|------|-----------|----------|
| 工具数 | 48→49 | 53→54 |
| 描述增强工具数 | 12 | 23（多 6 销售公式 + 战态公式也增强） |
| guide 公式主题 | 1 套（IVI/SPE/EWS） | 2 套（IVI/SPE/EWS + BQ/BSP/BWS/PV） |
| 贴纸情绪标注 | 好感/敌意/中性/暧昧 | 友好/抗拒/中性/意向 |
| 术语 | 对方/她/约会/表白 | 客户/会面/成交 |
