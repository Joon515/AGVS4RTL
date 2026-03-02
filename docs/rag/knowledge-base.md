# RAG 知识库配置与规范

本规范定义 RAG（Retrieval-Augmented Generation）系统的向量数据库配置、知识文档结构、检索策略与集成方式。

## 系统架构

```
自然语言需求 → Architect Agent → RAG 检索引擎
                                      ↓
                              向量数据库 (ChromaDB)
                                      ↓
                            知识文档 (HDL设计模式/历史案例)
                                      ↓
                              相似设计 + 最佳实践
                                      ↓
                              架构生成 + PPA评估
```

## 技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| **向量数据库** | ChromaDB | 轻量级、本地部署、Python原生 |
| **Embedding模型** | OpenAI text-embedding-3-small | 平衡性能与成本 |
| **文档格式** | Markdown + JSON | 人类可读 + 结构化元数据 |
| **检索策略** | 混合检索（语义+关键词） | 提高准确性 |

## 知识库目录结构

```
data/rag/
├── vector_db/                    # ChromaDB 持久化目录
│   ├── chroma.sqlite3            # 数据库文件
│   └── embeddings/               # 向量存储
├── knowledge_docs/               # 原始知识文档
│   ├── design_patterns/          # 设计模式库
│   │   ├── fifo.md
│   │   ├── axi_slave.md
│   │   ├── axi_interconnect.md
│   │   ├── pipeline_register.md
│   │   └── clock_domain_crossing.md
│   ├── protocols/                # 协议规范
│   │   ├── axi4_lite.md
│   │   ├── axi4_stream.md
│   │   ├── apb.md
│   │   └── wishbone.md
│   ├── best_practices/           # 最佳实践
│   │   ├── reset_strategy.md
│   │   ├── clock_gating.md
│   │   ├── synthesis_friendly.md
│   │   └── low_power_design.md
│   ├── error_cases/              # 常见错误与修复
│   │   ├── timing_violations.md
│   │   ├── race_conditions.md
│   │   └── metastability.md
│   └── historical/               # 历史案例
│       ├── project_001_uart.md
│       └── project_002_axi_reg.md
└── metadata/                     # 元数据与索引
    ├── collections.json          # Collection 配置
    └── tags.json                 # 标签分类
```

## 知识文档格式

### Markdown 模板

每个知识文档遵循统一格式：

```markdown
---
title: "AXI4-Lite Slave 接口设计模式"
category: "design_patterns"
tags: ["axi", "bus", "slave", "register"]
complexity: "medium"
hdl_language: ["verilog", "systemverilog"]
ppa_profile:
  area_gates: 800
  max_freq_mhz: 300
  power_mw: 5.2
last_updated: "2026-02-14"
---

# AXI4-Lite Slave 接口设计模式

## 概述
AXI4-Lite 是 ARM AMBA 总线协议的简化版本，适用于低吞吐量的寄存器访问场景。

## 模块结构
... (详细设计说明)

## 端口定义
```json
{
  "ports": [...]
}
```

## Verilog 代码模板
```verilog
module axi_slave #(
  parameter ADDR_WIDTH = 12,
  parameter DATA_WIDTH = 32
) (
  ...
);
```

## PPA 特性
- **面积**: ~800 GE (典型配置)
- **频率**: 300 MHz (28nm 工艺)
- **功耗**: ~5 mW @ 200MHz

## 验证要点
- 握手协议合规性
- 地址对齐检查
- 错误响应处理

## 常见陷阱
1. 未处理 BREADY 低电平场景
2. RVALID/RREADY 死锁
3. 地址译码延迟过大

## 参考资料
- ARM IHI0022E AMBA AXI Protocol Specification
```

### JSON 元数据结构

```json
{
  "doc_id": "design_patterns/axi_slave",
  "title": "AXI4-Lite Slave 接口设计模式",
  "category": "design_patterns",
  "tags": ["axi", "bus", "slave", "register"],
  "complexity": "medium",
  "hdl_language": ["verilog", "systemverilog"],
  "ppa_profile": {
    "area_gates": 800,
    "max_freq_mhz": 300,
    "power_mw": 5.2
  },
  "interfaces": ["AXI4-Lite"],
  "use_cases": ["寄存器文件", "配置接口", "状态监控"],
  "last_updated": "2026-02-14",
  "embedding_version": "text-embedding-3-small"
}
```

## ChromaDB Collection 配置

### Collection 定义

```json
{
  "collections": [
    {
      "name": "hdl_design_patterns",
      "description": "HDL 设计模式与参考实现",
      "metadata": {
        "category": "design_patterns",
        "embedding_model": "text-embedding-3-small",
        "dimension": 1536
      }
    },
    {
      "name": "protocol_specs",
      "description": "总线协议规范与握手时序",
      "metadata": {
        "category": "protocols"
      }
    },
    {
      "name": "best_practices",
      "description": "HDL 编码与综合最佳实践",
      "metadata": {
        "category": "best_practices"
      }
    },
    {
      "name": "error_patterns",
      "description": "常见错误模式与修复方案",
      "metadata": {
        "category": "error_cases"
      }
    }
  ]
}
```

### 初始化配置

```python
# data/rag/metadata/collections.json
{
  "chroma_config": {
    "persist_directory": "data/rag/vector_db",
    "embedding_function": "openai:text-embedding-3-small",
    "distance_metric": "cosine",
    "collection_metadata": {
      "hnsw:space": "cosine",
      "hnsw:construction_ef": 100,
      "hnsw:M": 16
    }
  }
}
```

## 检索策略

### 1. 混合检索（Hybrid Search）

结合语义相似度与关键词匹配：

```python
def hybrid_search(query: str, filters: dict) -> list:
    """
    混合检索策略：
    1. 语义检索（Embedding 相似度）
    2. 关键词过滤（tags, interfaces）
    3. 复杂度匹配（简单需求优先简单模式）
    """
    semantic_results = collection.query(
        query_texts=[query],
        n_results=10,
        where=filters
    )
    
    # 根据 PPA 约束重排序
    reranked = rerank_by_ppa(semantic_results, ppa_constraints)
    return reranked[:3]
```

### 2. 查询增强

将自然语言需求转换为结构化查询：

```python
# 用户输入
user_input = "实现一个200MHz的AXI寄存器文件"

# 增强查询
enhanced_query = {
    "text": user_input,
    "filters": {
        "tags": {"$in": ["axi", "register"]},
        "ppa_profile.max_freq_mhz": {"$gte": 200}
    },
    "complexity": "medium"
}
```

### 3. 上下文窗口

检索时包含相关文档：

- **主文档**: 最相似的设计模式
- **辅助文档**: 协议规范、最佳实践
- **反例文档**: 常见错误（用于规避）

## 知识库初始化流程

### 步骤 1: 准备知识文档

```bash
# 创建初始设计模式文档
data/rag/knowledge_docs/design_patterns/
├── fifo.md
├── axi_slave.md
├── axi_interconnect.md
└── pipeline_register.md
```

### 步骤 2: 生成 Embeddings

```python
from app.rag.knowledge_loader import KnowledgeLoader

loader = KnowledgeLoader(persist_dir="data/rag/vector_db")
loader.load_documents("data/rag/knowledge_docs/")
loader.build_index()
```

### 步骤 3: 验证检索

```python
results = loader.search("AXI-Lite 寄存器接口", n_results=3)
for doc in results:
    print(f"- {doc['title']} (相似度: {doc['score']})")
```

## Architect Agent 集成

### 工作流

```python
class ArchitectAgent:
    def __init__(self, rag_store):
        self.rag = rag_store
    
    def design(self, intent: dict, constraints: dict) -> dict:
        # 1. RAG 检索相似设计
        similar_designs = self.rag.search(
            query=intent["summary"],
            filters={
                "interfaces": {"$in": intent["interfaces"]},
                "ppa_profile.max_freq_mhz": {
                    "$gte": constraints["freq_target"]
                }
            }
        )
        
        # 2. 构建提示词（包含检索结果）
        prompt = self._build_prompt(intent, similar_designs)
        
        # 3. LLM 生成架构
        architecture = llm.generate(prompt)
        
        return architecture
```

## 知识库维护

### 定期更新

- **频率**: 每月添加新的成功案例
- **来源**: 历史项目、开源设计、用户反馈
- **质量控制**: Code Review + PPA 验证

### 版本控制

```json
{
  "knowledge_base_version": "v1.2",
  "last_updated": "2026-02-14",
  "changelog": [
    {
      "version": "v1.2",
      "date": "2026-02-14",
      "changes": [
        "添加 AXI-Stream 设计模式",
        "更新 FIFO 深度计算公式"
      ]
    }
  ]
}
```

## 性能优化

### 缓存策略

```python
# 缓存常见查询的检索结果
@lru_cache(maxsize=100)
def cached_search(query_hash: str) -> list:
    return rag_store.search(query)
```

### 批量检索

```python
# 批量处理多个模块的检索请求
def batch_search(queries: list[str]) -> list[list]:
    return collection.query(
        query_texts=queries,
        n_results=5
    )
```

## 相关配置文件

### app/rag/config.py

```python
RAG_CONFIG = {
    "persist_directory": "data/rag/vector_db",
    "embedding_model": "text-embedding-3-small",
    "collection_name": "hdl_design_patterns",
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "top_k": 3,
    "score_threshold": 0.7
}
```

## 相关文档

- [LangGraph State Schema](../architecture/state-schema.md)
- [端口与层次结构规范](../spec/ports-and-hierarchy.md)
- [PPA 报告格式](../ppa/report-format.md)
