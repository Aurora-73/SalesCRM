# SalesCRM 架构矫正完成记录

> 创建日期：2026-07-02  
> 原计划：`plan/矫正计划.md`（已归档至此）  
> 验收报告：`loveMentor/plan/SalesCRM矫正验收.md`  
> 状态：✅ **已完成**

---

## 一、矫正目标

将公式从"决策核心"降级为"辅助参考"，强化 Wiki 知识库的"推理主轴"定位。

| 组件 | 矫正前 | 矫正后 |
|------|--------|--------|
| OKF 知识库 | 补充参考 | **推理主轴**（Agent 的第一依据） |
| 事实档案 | 混入分析结论 | **长期记忆**（evidence layer） |
| 分析归档 | 混在事实档案里 | **独立层**（evaluation layer） |
| 公式 | 决策核心 | **辅助参考**（chat-skills 遗产） |
| 15 个指标 | 精确评分系统 | **辅助指标**（结构化数字摘要） |

---

## 二、完成的任务

### P0：文档定位矫正（6 项 + 1 子项）

| 任务 | 文件 | 关键改动 |
|------|------|---------|
| 1 | `readme/PROJECT.md` | 公式降级为"2.6 辅助参考"小节；架构图重构（Wiki 主轴）；数据优先级拆为操作顺序+冲突裁决两表；新增"2.5 Wiki 知识库"章节 |
| 2 | `readme/formulas.md` | 标题改为"公式参考（辅助视角）"；开篇声明 chat-skills 遗产；新增公式演进链条 + BQ 核验示例 |
| 3 | `.claude/skills/sales-crm.md` | 分析流程模板公式推荐降至 0%；知识库路径修正 `docs/sales/`→`docs/wiki/`；新增 Agent 分析风格指引 |
| 4 | `readme/mcp.md` | Wiki 工具标"推理第一依据"；公式工具标"辅助参考"；Wiki 工具排序靠前 |
| 5 | `engine/formulas_love.py` + `formulas_sales.py` | docstring 改为"辅助参考公式"；每个函数加"参考视角，不机械套用" |
| 6 | `engine/knowledge/wiki_context.py` | 修正"优先级低"表述为"Wiki 是方法论主轴"；提取 `_format_snippets`；添加空结果/低分命中 fallback |
| 6.5 | `CLAUDE.md` | 路径修正 `data/facts/people/`→`data/customers/`；补充自检三问 + 概念分层 |

### P1：公式与 Wiki 关系重建（3 项）

| 任务 | 关键改动 |
|------|---------|
| 7 | 7 个公式标注 Wiki 依据（IVI/SPE/EWS/Gap_Effect/BQ/BSP/BWS）；6 个无对应条目未标 |
| 8 | formulas.md 新增"公式演进链条"（chat-skills 遗产→软关联→回测校准→迭代优化）；BQ 核验示例 |
| 8.5 | wiki_context.py 和 sales-crm.md 加入 Wiki 检索 fallback 策略（空结果/低分命中/同义词重试） |

### P2：事实档案概念拆分（1 项）

| 任务 | 关键改动 |
|------|---------|
| 9 | facts.md 新增"概念分层：事实档案 vs 分析归档"（evidence/evaluation）；写入自检清单；`evaluate()` 归入分析归档 |

### P3：Wiki 检索测试补全（2 项）

| 任务 | 关键改动 |
|------|---------|
| 10 | 新建 `tests/test_wiki_retriever.py`，20 个测试函数全绿；fixture 构造 7 篇销售场景 OKF 文档；conftest.py 未改 |
| 10.5 | ⏭️ 跳过（docs/wiki/index.md 无计数声明） |

### P4：指标定位调整（2 项）

| 任务 | 关键改动 |
|------|---------|
| 11 | PROJECT.md 2.4 加入"15 个指标的本质"说明（辅助指标，非评分系统，embedding vector 同类） |
| 12 | metrics.py docstring 从"16 个 MetricValue 加权指标"改为"15 个辅助指标（结构化数字摘要）" |

### P5：规划更新（1 项）

| 任务 | 关键改动 |
|------|---------|
| 13 | `plan/next_steps.md` 新增"架构矫正"里程碑；方向 B 改为"基于 Wiki 知识的策略建议"；方向 D 新增 Wiki 测试；新增方向 F（Wiki 知识库扩充） |

### P6：未来计划（文档）

| 任务 | 关键改动 |
|------|---------|
| 14 | 创建 `readme/future_formula_wiki_metadata.md`：FORMULA_WIKI_MAP 结构化元数据方案 + 实施步骤 + 验收标准 |

---

## 三、测试结果

```
236 passed in 6.16s ✅
```

| 测试类别 | 数量 |
|---------|------|
| 原有测试 | 216 |
| 新增 Wiki 检索测试 | 20 |
| **总计** | **236** |

---

## 四、文档一致性验证

| 文档 | Wiki 定位 | 公式定位 | 一致 |
|------|----------|---------|------|
| `readme/PROJECT.md` | 2.5 推理主轴 | 2.6 辅助参考 | ✅ |
| `readme/formulas.md` | 推理主轴（开篇声明） | 辅助参考（标题+声明） | ✅ |
| `.claude/skills/sales-crm.md` | 知识库检索（推理主轴） | 辅助参考：公式工具（核验而非套用） | ✅ |
| `readme/mcp.md` | Wiki 工具优先（第一依据） | 公式工具（辅助参考） | ✅ |
| `CLAUDE.md` | 操作顺序①读 Wiki | 冲突裁决优先级 5（辅助参考） | ✅ |
| `wiki_context.py` | prompt header 推理主轴 | — | ✅ |

---

## 五、残留问题

| # | 问题 | 严重度 | 处理方式 |
|---|------|--------|---------|
| 1 | Wiki 覆盖不全（7/15 = 47%） | 🟡 中 | 方向 F 补齐 6 个条目 |
| 2 | 公式权重纯经验值 | 🟡 中 | P6 回测阶段 |
| 3 | 事实档案物理未分离 | 🟢 低 | 下一轮低优先级 |

---

## 六、下一轮矫正方向

| 方向 | 内容 | 优先级 |
|------|------|--------|
| Wiki 知识库扩充 | 补齐 IS→[[需求挖掘]]、EEV→[[成交期望值]] 等 6 个条目 | 中-高 |
| 公式-Wiki 结构化元数据 | FORMULA_WIKI_MAP + 自动校验 + MCP wiki_basis | 高 |
| 回测调参 | 用实际成交/流失案例校准公式权重和阈值 | 中 |
| Agent 行为端到端测试 | 真实 Agent 跑典型 case，验证推理顺序 | 中 |

---

## 七、参考链接

- [PROJECT.md](PROJECT.md) — 项目文档（2.5 Wiki 知识库 + 2.6 辅助参考）
- [formulas.md](formulas.md) — 公式参考（辅助视角，含演进链条）
- [facts.md](facts.md) — 事实档案概念分层 + 自检清单
- [mcp.md](mcp.md) — MCP 工具文档
- [future_formula_wiki_metadata.md](future_formula_wiki_metadata.md) — P6 未来计划
- 验收报告：`loveMentor/plan/SalesCRM矫正验收.md`
