# Prompt Templates - Jinja2 模板系统

## 概述

为实现提示词与代码的分离，AGVS4RTL 采用 **Jinja2 模板引擎**管理所有 LLM 提示词。

## 设计目标

- ✅ **解耦**: 提示词独立于 Python 代码，便于维护和版本控制
- ✅ **可测试性**: 支持提示词 A/B 测试和性能评估
- ✅ **复用性**: 通过继承和包含机制复用通用模板片段
- ✅ **审计性**: 提示词变更可追溯，便于调试和优化

## 目录结构

```
app/
└── prompts/
    ├── __init__.py
    ├── loader.py                     # Jinja2 加载器封装
    ├── base.j2                       # 基础模板 (通用指令)
    ├── parser/
    │   ├── extract_intent.j2         # 需求解析主模板
    │   ├── validate_spec.j2          # 规范验证模板
    │   └── examples/                 # Few-shot 示例片段
    │       ├── axi_example.j2
    │       └── uart_example.j2
    ├── architect/
    │   ├── design_proposal.j2        # 架构设计提案生成
    │   ├── module_decomposition.j2   # 模块分解指令
    │   ├── ppa_estimation.j2         # PPA 评估指令
    │   └── rag_context.j2            # RAG 检索上下文注入
    ├── generator/
    │   ├── hdl_generation.j2         # HDL 代码生成主模板
    │   ├── interface_generation.j2   # 接口代码生成
    │   ├── testbench_generation.j2   # Testbench 生成
    │   └── style_guide.j2            # Coding Style 片段
    └── test/
        ├── uvm_test_generation.j2    # UVM 测试生成
        ├── coverage_analysis.j2      # 覆盖率分析指令
        └── error_diagnosis.j2        # 错误诊断提示
```

## PromptLoader 接口规范

### 核心类

```python
from jinja2 import Environment, FileSystemLoader, select_autoescape
from typing import Dict, Any, Optional

class PromptLoader:
    """Jinja2 提示词模板加载器"""
    
    def __init__(self, template_dir: str = "app/prompts"):
        """初始化模板环境
        
        Args:
            template_dir: 模板根目录路径
        """
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['j2']),
            trim_blocks=True,        # 移除块后的第一个换行
            lstrip_blocks=True,      # 移除块前的空白
            keep_trailing_newline=True
        )
        
        # 注册自定义过滤器
        self.env.filters['code_escape'] = self._code_escape
        self.env.filters['json_format'] = self._json_format
    
    def render(self, template_name: str, **context) -> str:
        """渲染模板
        
        Args:
            template_name: 模板文件名 (相对于 template_dir)
            **context: 模板变量
            
        Returns:
            渲染后的提示词字符串
            
        Example:
            >>> loader = PromptLoader()
            >>> prompt = loader.render(
            ...     "parser/extract_intent.j2",
            ...     requirement="实现一个UART模块",
            ...     target_language="verilog"
            ... )
        """
        template = self.env.get_template(template_name)
        return template.render(**context)
    
    @staticmethod
    def _code_escape(text: str) -> str:
        """转义代码块中的特殊字符"""
        return text.replace("```", "\\```")
    
    @staticmethod
    def _json_format(obj: Any, indent: int = 2) -> str:
        """格式化 JSON 对象"""
        import json
        return json.dumps(obj, ensure_ascii=False, indent=indent)
```

## 模板编写规范

### 1. 基础模板 (base.j2)

定义所有提示词的通用指令和格式约束：

```jinja2
{# base.j2 - 基础模板 #}
你是一个专业的硬件设计专家，精通 HDL 设计和验证。

**通用规则:**
- 所有输出必须符合指定的 JSON Schema
- 使用标准的 HDL 命名规范
- 注重代码可综合性和可测试性
- 提供详细的注释说明

{% block specific_instructions %}
{# 子模板覆盖此块 #}
{% endblock %}

{% block output_format %}
{# 子模板定义输出格式 #}
{% endblock %}
```

### 2. 解析器模板示例 (parser/extract_intent.j2)

```jinja2
{% extends "base.j2" %}

{% block specific_instructions %}
**任务**: 从自然语言需求中提取结构化的设计意图

**分析要点:**
1. **核心功能**: 识别主要功能模块和数据流
2. **接口协议**: 检测 AXI, APB, UART, SPI 等标准接口
3. **时钟复位**: 提取时钟信号名和复位极性
4. **约束条件**: 区分硬约束(必须)和软约束(优化目标)

**用户需求:**
{{ requirement }}

{% if examples %}
**参考示例:**
{% for example in examples %}
- {{ example.description }}: {{ example.result }}
{% endfor %}
{% endif %}
{% endblock %}

{% block output_format %}
**输出格式 (JSON):**
```json
{
  "intent": {
    "summary": "功能摘要",
    "target_language": "{{ target_language | default('verilog') }}",
    "clock": "clk",
    "reset": "rst_n",
    "interfaces": ["axi-lite"]
  },
  "constraints": {
    "hard": [
      {"type": "frequency", "value": 100, "unit": "MHz"}
    ],
    "soft": [
      {"type": "optimization", "target": "area"}
    ]
  }
}
```
{% endblock %}
```

### 3. 架构设计模板示例 (architect/design_proposal.j2)

```jinja2
{% extends "base.j2" %}

{% block specific_instructions %}
**任务**: 生成模块化架构设计方案

**设计意图:**
{{ design_intent | json_format }}

{% if rag_context %}
**相关设计参考 (RAG 检索结果):**
{% for doc in rag_context %}
### {{ doc.title }}
{{ doc.content }}
{% endfor %}
{% endif %}

**设计要求:**
1. 采用层次化设计，模块职责单一
2. 接口遵循 {{ protocol }} 协议规范
3. 考虑可测试性，预留调试接口
4. PPA 目标: 面积 < {{ ppa_target.area }}mm², 功耗 < {{ ppa_target.power }}mW
{% endblock %}

{% block output_format %}
**输出格式:**
```json
{
  "architecture": {
    "top_module": "design_top",
    "hierarchy": [
      {
        "name": "module_name",
        "level": 0,
        "ports": [...],
        "dependencies": []
      }
    ]
  },
  "ppa_estimation": {
    "area": {"value": 0.5, "unit": "mm²"},
    "power": {"value": 10, "unit": "mW"},
    "frequency": {"value": 100, "unit": "MHz"}
  }
}
```
{% endblock %}
```

## 使用示例

### Agent 中集成 PromptLoader

```python
# app/pre_agent/parser_agent.py

from app.prompts.loader import PromptLoader

class ParserAgent:
    def __init__(self, llm: ChatOpenAI):
        self.llm = llm
        self.prompt_loader = PromptLoader()
    
    async def parse_requirement(self, requirement: str) -> PreprocessOutput:
        """使用模板生成提示词并调用 LLM"""
        
        # 加载 few-shot 示例
        examples = self._load_examples()
        
        # 渲染模板
        prompt = self.prompt_loader.render(
            "parser/extract_intent.j2",
            requirement=requirement,
            target_language="verilog",
            examples=examples
        )
        
        # 调用 LLM
        response = await self.llm.ainvoke([
            SystemMessage(content=prompt)
        ])
        
        return self._parse_response(response.content)
```

## 模板版本管理

### 提示词版本控制策略

```
app/prompts/
├── v1/                         # 版本 1 (稳定版)
│   └── parser/
│       └── extract_intent.j2
├── v2/                         # 版本 2 (实验版)
│   └── parser/
│       └── extract_intent.j2
└── active -> v1/               # 符号链接指向当前版本
```

### 版本切换

```python
class PromptLoader:
    def __init__(self, version: str = "active"):
        template_dir = f"app/prompts/{version}"
        # ... 初始化逻辑
```

## A/B 测试支持

```python
from enum import Enum

class PromptVersion(Enum):
    V1_BASELINE = "v1"
    V2_EXPERIMENTAL = "v2"

async def parse_with_ab_test(requirement: str, version: PromptVersion):
    loader = PromptLoader(version=version.value)
    # ... 执行解析
    
    # 记录性能指标
    log_prompt_performance(version, accuracy, latency)
```

## 自定义过滤器

Jinja2 支持扩展自定义过滤器，用于特殊格式化：

```python
def register_custom_filters(env: Environment):
    """注册自定义过滤器"""
    
    @env.filter
    def verilog_escape(text: str) -> str:
        """转义 Verilog 关键字"""
        keywords = {'module', 'endmodule', 'input', 'output'}
        # ... 转义逻辑
        return escaped_text
    
    @env.filter
    def port_format(ports: list) -> str:
        """格式化端口列表为 Verilog 语法"""
        lines = []
        for port in ports:
            lines.append(f"    {port['direction']} [{port['width']-1}:0] {port['name']}")
        return ",\n".join(lines)
```

## 最佳实践

### 1. 模板组织原则
- **单一职责**: 每个模板只负责一个特定任务
- **DRY 原则**: 复用通用片段，避免重复
- **语义化命名**: 模板名清晰表达用途

### 2. 变量命名规范
- 使用 `snake_case` 命名变量
- 布尔变量以 `is_`, `has_`, `enable_` 开头
- 列表变量使用复数形式

### 3. 注释与文档
```jinja2
{# 
  模板: extract_intent.j2
  用途: 需求解析与结构化提取
  变量:
    - requirement (str): 用户输入的自然语言需求
    - target_language (str): 目标 HDL 语言 (默认: verilog)
    - examples (list, optional): Few-shot 示例列表
  输出: JSON 格式的 PreprocessOutput
#}
```

### 4. 条件渲染
```jinja2
{% if enable_rag %}
**相关设计参考:**
{{ rag_context }}
{% endif %}

{% if complexity == "high" %}
建议采用分层设计策略
{% else %}
可以使用单模块实现
{% endif %}
```

## 性能优化

### 1. 模板缓存
```python
class PromptLoader:
    def __init__(self):
        self.env = Environment(
            loader=FileSystemLoader("app/prompts"),
            cache_size=400  # 缓存最近使用的 400 个模板
        )
```

### 2. 延迟加载
```python
from functools import lru_cache

class PromptLoader:
    @lru_cache(maxsize=128)
    def render(self, template_name: str, **context) -> str:
        # 相同参数的模板调用直接返回缓存结果
        pass
```

## 测试策略

### 单元测试示例

```python
# tests/test_prompts.py

import pytest
from app.prompts.loader import PromptLoader

def test_parser_template_rendering():
    loader = PromptLoader()
    
    prompt = loader.render(
        "parser/extract_intent.j2",
        requirement="实现一个 UART 模块",
        target_language="verilog"
    )
    
    assert "UART" in prompt
    assert "verilog" in prompt
    assert "JSON" in prompt

def test_template_with_rag_context():
    loader = PromptLoader()
    
    rag_docs = [
        {"title": "FIFO 设计", "content": "标准 FIFO 实现..."}
    ]
    
    prompt = loader.render(
        "architect/design_proposal.j2",
        design_intent={"summary": "实现 FIFO"},
        rag_context=rag_docs,
        protocol="AXI-Stream"
    )
    
    assert "FIFO 设计" in prompt
    assert "AXI-Stream" in prompt
```

## 迁移路径

### Phase 1: 准备阶段
1. 创建 `app/prompts/` 目录结构
2. 实现 `PromptLoader` 类
3. 编写基础模板和测试用例

### Phase 2: 迁移阶段
1. 将 `ParserAgent` 的硬编码提示词迁移到模板
2. 验证输出一致性
3. 逐步迁移其他 Agent

### Phase 3: 优化阶段
1. 添加 RAG 上下文注入模板
2. 实现 A/B 测试框架
3. 建立提示词性能监控

## 相关文档

- [State Schema 规范](./state-schema.md)
- [Design Intent 规范](../spec/design-intent.md)
- [Agent 配置规范](../spec/agent-config.md)

---

**版本**: v1.0  
**最后更新**: 2026-02-19  
**维护者**: AGVS4RTL Team
