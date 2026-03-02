# Jinja2 提示词模板系统开发任务

## 任务概述

在下一次开发对话中，实现 Jinja2 提示词模板系统并迁移现有的硬编码提示词到模板文件。

## 开发目标

### 核心目标
- ✅ 创建 `app/prompts/` 模板目录结构
- ✅ 实现 `PromptLoader` 类及其核心功能
- ✅ 迁移 `ParserAgent` 的硬编码提示词到 Jinja2 模板
- ✅ 编写单元测试验证模板渲染准确性
- ✅ 更新 `requirements.txt` 添加 Jinja2 依赖

### 扩展目标（可选）
- 🔲 为其他 Agent (Architect, Generator) 创建模板占位符
- 🔲 实现模板版本管理机制
- 🔲 添加性能监控和缓存机制

## 实施步骤

### Step 1: 准备基础设施

#### 1.1 创建目录结构
```bash
mkdir -p app/prompts/parser
mkdir -p app/prompts/architect
mkdir -p app/prompts/generator
mkdir -p app/prompts/test
```

#### 1.2 更新依赖
在 `requirements.txt` 中添加:
```
jinja2>=3.1.2
```

### Step 2: 实现 PromptLoader 类

**文件**: `app/prompts/loader.py`

**功能需求**:
1. 使用 Jinja2 `Environment` 和 `FileSystemLoader`
2. 配置模板环境参数:
   - `trim_blocks=True` - 移除块后换行
   - `lstrip_blocks=True` - 移除块前空白
   - `autoescape` - 防止XSS (对于代码生成可禁用)
3. 实现 `render(template_name, **context)` 方法
4. 添加自定义过滤器:
   - `code_escape` - 转义代码块
   - `json_format` - 格式化JSON输出

**参考实现**:
```python
from jinja2 import Environment, FileSystemLoader, select_autoescape
import json
from typing import Any, Dict, Optional

class PromptLoader:
    """Jinja2 提示词模板加载器"""
    
    def __init__(self, template_dir: str = "app/prompts"):
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['j2']),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True
        )
        
        # 注册自定义过滤器
        self.env.filters['code_escape'] = self._code_escape
        self.env.filters['json_format'] = self._json_format
    
    def render(self, template_name: str, **context) -> str:
        """渲染模板"""
        template = self.env.get_template(template_name)
        return template.render(**context)
    
    @staticmethod
    def _code_escape(text: str) -> str:
        """转义代码块中的特殊字符"""
        return text.replace("```", "\\```")
    
    @staticmethod
    def _json_format(obj: Any, indent: int = 2) -> str:
        """格式化 JSON 对象"""
        return json.dumps(obj, ensure_ascii=False, indent=indent)
```

### Step 3: 创建基础模板

**文件**: `app/prompts/base.j2`

```jinja2
{# base.j2 - 所有提示词的基础模板 #}
你是一个专业的硬件设计专家，精通 HDL 设计和验证。

**通用规则:**
- 所有输出必须符合指定的 JSON Schema
- 使用标准的 HDL 命名规范 (小写+下划线)
- 注重代码可综合性和可测试性
- 提供清晰的中文注释

{% block specific_instructions %}
{# 子模板在此定义具体任务指令 #}
{% endblock %}

{% block context %}
{# 子模板在此注入上下文信息 #}
{% endblock %}

{% block output_format %}
{# 子模板在此定义输出格式 #}
{% endblock %}
```

### Step 4: 迁移 ParserAgent 提示词

**文件**: `app/prompts/parser/extract_intent.j2`

```jinja2
{% extends "base.j2" %}

{% block specific_instructions %}
**任务**: 从自然语言需求中提取结构化的设计意图和约束条件

**分析要点:**
1. **设计意图 (Design Intent)**:
   - 核心功能摘要
   - 目标HDL语言 (Verilog/SystemVerilog/VHDL)
   - 时钟信号名称
   - 复位信号名称（注意低电平有效 rst_n vs 高电平有效 rst）
   - 接口协议关键词 (AXI, APB, AXI-Stream, UART, SPI等)

2. **约束条件 (Constraints)**:
   - **硬约束 (Hard)**: 必须满足的要求（频率、数据位宽等）
   - **软约束 (Soft)**: 优化目标（面积最小化、功耗最小化等）
{% endblock %}

{% block context %}
**用户需求:**
{{ requirement }}

{% if examples %}
**参考示例:**
{% for example in examples %}
{{ loop.index }}. **{{ example.description }}**
   需求: {{ example.requirement }}
   提取结果: {{ example.result | json_format }}
{% endfor %}
{% endif %}
{% endblock %}

{% block output_format %}
**输出格式 (纯 JSON，无其他文字):**
```json
{
  "intent": {
    "summary": "功能摘要，保留原始语义",
    "target_language": "{{ target_language | default('verilog') }}",
    "clock": "clk",
    "reset": "rst_n",
    "interfaces": ["接口协议关键词列表"]
  },
  "constraints": {
    "hard": [
      {
        "type": "frequency|data_width|address_width",
        "value": 数值,
        "unit": "单位"
      }
    ],
    "soft": [
      {
        "type": "optimization",
        "target": "area|power|latency"
      }
    ]
  }
}
```

**重要提示:**
- 如果需求中未明确提及某些字段，使用 `null` 或空列表
- `summary` 必须保留用户的原始需求语义
- 接口协议关键词全部小写，使用连字符 (如 "axi-lite")
{% endblock %}
```

### Step 5: 修改 ParserAgent 集成模板

**文件**: `app/pre_agent/parser_agent.py`

**需要修改的部分**:

```python
from app.prompts.loader import PromptLoader

class ParserAgent:
    """LLM-powered parser for HDL requirement extraction."""
    
    def __init__(self, llm: Optional[ChatOpenAI] = None):
        """初始化 ParserAgent
        
        Args:
            llm: LangChain ChatOpenAI 实例
        """
        self.llm = llm or self._create_default_llm()
        self.prompt_loader = PromptLoader()  # 新增
    
    async def parse(self, requirement: str) -> PreprocessOutput:
        """解析用户需求并提取结构化信息
        
        Args:
            requirement: 自然语言需求描述
            
        Returns:
            PreprocessOutput: 包含 intent 和 constraints 的结构化输出
        """
        # 使用模板生成提示词
        prompt = self.prompt_loader.render(
            "parser/extract_intent.j2",
            requirement=requirement,
            target_language="verilog",
            examples=self._get_few_shot_examples()  # 可选
        )
        
        # 调用 LLM
        messages = [SystemMessage(content=prompt)]
        response = await self.llm.ainvoke(messages)
        
        # 解析响应
        return self._parse_response(response.content)
    
    def _get_few_shot_examples(self) -> list:
        """获取 Few-shot 示例（可选）"""
        return [
            {
                "description": "AXI-Lite 寄存器文件",
                "requirement": "实现一个带AXI-Lite接口的寄存器文件",
                "result": {
                    "intent": {
                        "summary": "实现一个带AXI-Lite接口的寄存器文件",
                        "target_language": "verilog",
                        "clock": "clk",
                        "reset": "rst_n",
                        "interfaces": ["axi-lite"]
                    },
                    "constraints": {"hard": [], "soft": []}
                }
            }
        ]
```

**关键修改点**:
1. 删除 `SYSTEM_PROMPT` 类变量
2. 在 `__init__` 中初始化 `PromptLoader`
3. 在 `parse` 方法中使用 `prompt_loader.render()`
4. 可选: 添加 `_get_few_shot_examples()` 方法

### Step 6: 编写单元测试

**文件**: `tests/test_prompt_loader.py`

```python
import pytest
from app.prompts.loader import PromptLoader

def test_prompt_loader_initialization():
    """测试 PromptLoader 初始化"""
    loader = PromptLoader()
    assert loader.env is not None

def test_render_parser_template():
    """测试解析器模板渲染"""
    loader = PromptLoader()
    
    prompt = loader.render(
        "parser/extract_intent.j2",
        requirement="实现一个UART发送器",
        target_language="verilog"
    )
    
    assert "UART" in prompt
    assert "verilog" in prompt
    assert "intent" in prompt
    assert "constraints" in prompt

def test_render_with_examples():
    """测试带示例的模板渲染"""
    loader = PromptLoader()
    
    examples = [
        {
            "description": "测试示例",
            "requirement": "示例需求",
            "result": {"intent": {}, "constraints": {}}
        }
    ]
    
    prompt = loader.render(
        "parser/extract_intent.j2",
        requirement="测试需求",
        examples=examples
    )
    
    assert "测试示例" in prompt
    assert "参考示例" in prompt

def test_json_format_filter():
    """测试 JSON 格式化过滤器"""
    loader = PromptLoader()
    
    template_str = "{{ data | json_format }}"
    template = loader.env.from_string(template_str)
    
    result = template.render(data={"key": "值"})
    assert '"key": "值"' in result or '"key":"值"' in result
```

**文件**: `tests/test_parser_agent_with_templates.py`

```python
import pytest
import asyncio
from app.pre_agent.parser_agent import ParserAgent

@pytest.mark.asyncio
async def test_parser_with_template():
    """测试 ParserAgent 使用模板进行解析"""
    agent = ParserAgent()
    
    result = await agent.parse("实现一个UART接收器，波特率9600")
    
    assert result.intent.summary is not None
    assert "uart" in result.intent.summary.lower()
    assert result.intent.target_language == "verilog"

@pytest.mark.asyncio
async def test_parser_template_renders_correctly():
    """验证模板渲染的提示词格式正确"""
    agent = ParserAgent()
    
    # 直接测试模板渲染
    prompt = agent.prompt_loader.render(
        "parser/extract_intent.j2",
        requirement="测试需求",
        target_language="systemverilog"
    )
    
    assert "测试需求" in prompt
    assert "systemverilog" in prompt
    assert "输出格式" in prompt
```

### Step 7: 集成测试

创建端到端测试验证整个流程：

```python
# tests/test_integration_parser.py

import pytest
from app.pre_agent.parser_agent import ParserAgent
from app.pre_agent.stracture_request import PreprocessOutput

@pytest.mark.asyncio
async def test_end_to_end_parsing():
    """端到端测试: 从需求到结构化输出"""
    agent = ParserAgent()
    
    requirement = """
    实现一个AXI-Lite从设备，包含16个32位寄存器。
    时钟频率100MHz，低电平异步复位。
    要求面积最小化。
    """
    
    result = await agent.parse(requirement)
    
    # 验证输出结构
    assert isinstance(result, PreprocessOutput)
    assert "axi-lite" in result.intent.interfaces
    assert result.intent.reset == "rst_n"
    assert any(c.type == "frequency" for c in result.constraints.hard)
    assert any(c.target == "area" for c in result.constraints.soft)
```

## 验收标准

### 功能验收
- [ ] `PromptLoader` 可以成功加载和渲染模板
- [ ] `ParserAgent.parse()` 使用模板生成提示词并正确解析
- [ ] 输出格式与之前硬编码版本完全一致
- [ ] 所有现有测试仍然通过

### 代码质量验收
- [ ] 所有新增代码包含类型注解
- [ ] 所有新增函数包含 docstring
- [ ] 代码遵循 PEP 8 规范
- [ ] 单元测试覆盖率 > 80%

### 文档验收
- [ ] `PromptLoader` 类有完整的 API 文档
- [ ] 模板文件包含注释说明变量和用途
- [ ] README 或开发文档更新使用说明

## 注意事项与最佳实践

### 开发顺序建议
1. **先创建基础设施** (loader.py, 目录结构)
2. **再创建简单模板** (base.j2, extract_intent.j2)
3. **然后修改 Agent 集成**
4. **最后编写测试验证**

### 常见陷阱
- ⚠️ Jinja2 默认会自动转义 HTML，对于代码生成需要禁用或配置合适的 autoescape
- ⚠️ 模板路径是相对于 `template_dir`，注意使用正确的路径分隔符
- ⚠️ 渲染时传入的变量名必须与模板中的变量名完全匹配

### 调试技巧
```python
# 在开发时启用模板调试
from jinja2 import DebugUndefined

env = Environment(
    loader=FileSystemLoader("app/prompts"),
    undefined=DebugUndefined  # 未定义变量不会静默失败
)
```

## 后续优化方向

完成基础实施后，可以考虑以下优化：

1. **性能优化**
   - 添加模板缓存机制
   - 使用 `@lru_cache` 缓存渲染结果

2. **功能扩展**
   - 实现模板版本管理 (v1/, v2/)
   - 添加 A/B 测试支持
   - 实现提示词性能监控

3. **工具支持**
   - 创建模板 linting 工具
   - 添加模板热重载 (开发环境)
   - 开发模板可视化预览工具

## 参考资料

- [Jinja2 官方文档](https://jinja.palletsprojects.com/)
- [Jinja2 模板继承](https://jinja.palletsprojects.com/en/3.1.x/templates/#template-inheritance)
- [LangChain 提示词最佳实践](https://python.langchain.com/docs/modules/model_io/prompts/)
- [项目提示词模板规范](../docs/architecture/prompt-templates.md)

---

**准备开始开发了吗？** 在下一次对话中说"开始实现 Jinja2 模板系统"即可开始！

如有任何问题，请参考 [docs/architecture/prompt-templates.md](../docs/architecture/prompt-templates.md) 了解完整的设计规范。
