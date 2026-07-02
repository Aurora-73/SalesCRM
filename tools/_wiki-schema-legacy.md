---
type: Schema
title: Wiki Schema
description: SalesCRM Wiki 的结构定义和格式规范。
timestamp: 2026-07-01T00:00:00Z
---
# Wiki Schema

> SalesCRM Wiki 的结构定义和格式规范。

## 目录结构

```
wiki/
├── index.md              # 首页导航
├── .wiki-schema.md       # 本文件：结构定义
├── entities/             # 实体（概念、技术、模型）
├── scenarios/            # 场景（具体问题的解决方案）
├── topics/               # 主题（跨实体的知识整合）
├── sources/              # 来源（原始资料、课程笔记）
└── synthesis/            # 综合分析（跨模块对比、元分析）
```

## 文件格式规范

### Frontmatter（必需）

所有 Wiki 页面必须包含 YAML frontmatter：

```yaml
---
type: Concept|Scenario|Topic|Source|Synthesis|Index|Schema
title: 页面标题
description: 页面描述（一句话）
tags: [标签1, 标签2, ...]
timestamp: 2026-07-01T00:00:00Z
# 以下为可选字段
entity_type: 概念|技术|模型|框架
scenarios: [reply, ask, analyze, meet]
confidence: EXTRACTED|INFERRED|SYNTHESIZED
search_terms: [搜索词1, 搜索词2, ...]
---
```

### 实体页面（entities/）

实体是 Wiki 的核心单元，包括：

| 类型 | 说明 | 示例 |
|------|------|------|
| **概念** | 核心心理学概念 | 冷读术、框架、社交认证 |
| **技术** | 可操作的沟通技术 | 讲故事技术、给台阶技术、收场技术 |
| **模型** | 分析框架和决策模型 | GTO决策框架、心理缺口模型 |

### 场景页面（scenarios/）

场景页面解决具体问题，格式：

1. 核心问题描述
2. 判断维度/信号识别
3. 分阶段策略
4. 常见错误
5. 相关实体链接

### 主题页面（topics/）

主题是跨实体的知识整合，格式：

1. 主题定义
2. 相关实体列表
3. 主题框架
4. 应用场景

### 来源页面（sources/）

来源页面记录原始资料，格式：

1. 资料基本信息
2. 核心观点摘要
3. 关键技术提取
4. 相关实体链接

### 综合分析页面（synthesis/）

综合分析是跨模块的深度对比，格式：

1. 分析主题
2. 对比维度
3. 各模块对比表
4. 综合结论

## 命名规范

- 使用中文标题，不含特殊字符
- 文件名 = 标题.md
- 目录名使用英文复数：entities, scenarios, topics, sources, synthesis

## 链接规范

- 内部链接使用相对路径：`[冷读术](冷读术.md)`
- 跨目录链接使用相对路径：`[冷读术](../entities/冷读术.md)`
- 外部链接使用完整 URL：`[来源: 冷读术（石井裕之）](https://...)`

## 标签规范

- 使用中文标签，简洁明了
- 核心实体使用 `核心概念`、`核心技术` 标签
- 场景页面使用 `场景` 标签
- 按功能分类：`沟通`、`分析`、`决策`、`关系`

## 版本控制

- 使用 timestamp 字段记录创建/更新时间
- 重大变更更新 timestamp
- 保留历史版本在 git 中

## 搜索优化

- search_terms 字段包含用户可能搜索的关键词
- tags 字段用于分类浏览
- description 字段用于搜索摘要