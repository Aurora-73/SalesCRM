# SalesCRM

AI 驱动的本地销售客户分析助手。基于微信聊天记录，自动分析客户意向、识别销售时机、提供跟进建议。

## 核心原则

代码负责数据，Agent 负责推理。

## 快速开始

详细架构和工具文档见 `readme/PROJECT.md` 和 `readme/` 下的模块文档。

## 目录结构

```
SalesCRM/
├── engine/          # 核心引擎
│   ├── tools.py     # 工具函数入口
│   ├── config.py    # 配置管理
│   ├── identity.py  # 身份目录
│   ├── agent/       # Agent 层
│   └── analyzers/   # 分析器
├── readme/          # 项目文档
├── data/            # 数据目录
└── docs/sales/      # 销售知识库
```