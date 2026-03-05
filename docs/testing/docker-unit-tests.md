# Docker 单元测试指南

## 概述

本文档说明如何在 Docker 容器中运行 AGVS4RTL 的单元测试。开发脚本已统一至 `app/dev_tests/`，其中 `app/dev_tests/run_pre_manager_unit_basic.py` 设计为无需 LLM API 密钥即可验证核心模块的结构和逻辑。

## 测试范围

### 版本边界（当前版本）

- 当前版本实现两类测试：
   - 静态单元测试（Pre-Manager 阶段）
   - TestAgent 模块级非静态执行测试（Verilator + pyuvm，Docker Sandbox）
- 图结构测试（循环依赖、层次深度、孤立模块等）仍在下一版本补齐。
- 下一版本相关能力落地时，结构化解析与验证仍采用 AST 方法，不使用 Regex 做模块层次与端口语义解析。

### 已覆盖模块（Pre-Manager Agent 阶段）

1. **State Schema** (`app/manage_agent/state_schema.py`)
   - AGVSState TypedDict 12个字段验证
   - `create_initial_state()` 初始化逻辑

2. **Preprocessor** (`app/pre_agent/structure_request.py`)
   - RequestData 数据结构
   - `to_state()` 转换方法

3. **PPA Estimator** (`app/manage_agent/ppa_estimator.py`)
   - 门数、功耗、时序计算逻辑
   - 可行性评估（HIGH/MEDIUM/LOW）
   - 警告机制

4. **RAG Module** (`app/rag/vector_store.py`)
   - RAGVectorStore 和 KnowledgeLoader 类结构
   - ChromaDB 可选依赖检测

5. **Parser Agent** (`app/pre_agent/parser_agent.py`)
   - 静态方法 `_fallback_parse()` 规则匹配逻辑
   - 接口识别（axi, apb, uart, spi）
   - 约束提取（frequency, data_width）

6. **Architect Agent** (`app/manage_agent/architect_agent.py`)
   - 静态方法 `_fallback_architecture()` 基础架构生成
   - 模块层次树结构

7. **Workflow** (`app/workflow.py`)
   - LangGraph 工作流编译
   - 3节点图（parser → architect → ppa_estimator）
   - 4节点扩展图（parser → architect → ppa_estimator → manager）

8. **Manager Agent** (`app/manage_agent/manager_agent.py`)
   - 静态模块编排（leaf → mid → ip → top）
   - retry/loop budget 状态推进
   - `architecture_validation` 延期占位回写（AST 边界声明）

9. **File Structure**
   - 核心 Python 文件存在性验证

10. **Test Agent（新增）**
   - `app/test_agent/test_unit_basic.py`：测试模板与状态回写的单元验证
   - `app/dev_tests/run_test_agent_docker_integration.py`：容器端到端执行验证
   - 覆盖率产物链路：`coverage.dat -> *.info -> state.coverage`

## 运行测试

### 前置条件

确保 Docker 容器正在运行：
```bash
docker compose ps
```

应看到两个容器：
- `hdl_agent_core` (STATUS: Up)
- `hdl_sandbox` (STATUS: Up)

### 执行测试

在项目根目录运行：
```bash
docker compose exec agent-core python3 app/dev_tests/run_pre_manager_unit_basic.py
```

TestAgent 单元测试（无 sandbox 依赖）：

```bash
docker compose exec -T agent-core python3 - <<'PY'
from pathlib import Path
import tempfile
from app.test_agent.test_unit_basic import test_test_agent_generates_templates_and_state

tmpdir = Path(tempfile.mkdtemp(prefix='agvs_test_agent_unit_'))
test_test_agent_generates_templates_and_state(tmpdir)
print('unit ok', tmpdir)
PY
```

TestAgent 集成测试（真实 sandbox 执行）：

```bash
timeout 300s docker compose exec -T agent-core python3 app/dev_tests/run_test_agent_docker_integration.py
```

### 预期输出

成功运行时的输出示例：
```
======================================================================
🧪 AGVS4RTL 单元测试套件 (无 LLM 依赖)
======================================================================

======================================================================
测试 1: State Schema 结构验证
======================================================================
✅ State Schema 结构正确
  - intent: 测试需求
  - 硬约束数量: 1
  - 迭代预算: 10

... (其他测试) ...

======================================================================
📊 测试结果汇总
======================================================================
✅ 通过: 9/9
❌ 失败: 0/9

🎉 所有测试通过！
```

## 测试设计原则

### 无 LLM 依赖

测试套件设计为**不需要 OpenAI API 密钥**，通过以下策略实现：

1. **静态方法测试**: 使用 `types.SimpleNamespace()` 模拟对象绑定静态方法
   ```python
   import types
   parser = types.SimpleNamespace()
   parser._fallback_parse = ParserAgent._fallback_parse.__get__(parser, ParserAgent)
   result = parser._fallback_parse("用户输入")
   ```

2. **逻辑验证**: 测试 fallback 机制（正则表达式、规则引擎）而非 LLM 调用

3. **结构验证**: 检查类定义、方法签名、数据结构完整性

### 容器隔离

- 测试在 `agent-core` 容器中运行
- 使用容器内的 Python 环境和依赖
- 不需要主机环境配置

### 可选依赖处理

- **ChromaDB**: 测试检测其存在但不要求安装
- 警告信息: `⚠️  ChromaDB 未安装（可选依赖）`

## 故障排查

### 问题: OpenAI API Key 错误

**症状**:
```
❌ Parser Agent 测试异常: The api_key client option must be set...
```

**原因**: 代码尝试实例化 `ParserAgent()` 或 `ArchitectAgent()`

**解决**: 确认测试使用静态方法测试模式（已在 2024-02-14 修复）

### 问题: 文件不存在

**症状**:
```
❌ 缺少文件: docs/architecture/state-schema.md
```

**原因**: `docs/` 目录未挂载到 Docker 容器

**解决**: 测试仅验证 `app/` 目录文件（已在 2024-02-14 修复）

### 问题: 导入错误

**症状**:
```
ModuleNotFoundError: No module named 'xxx'
```

**原因**: 依赖未安装或路径配置错误

**解决**: 
1. 检查 `requirements.txt` 是否完整
2. 验证容器内 Python 路径：`docker compose exec agent-core python3 -c "import sys; print(sys.path)"`

## 测试维护

### 添加新测试

在 `app/dev_tests/run_pre_manager_unit_basic.py` 的 `main()` 函数中注册：
```python
tests = [
    ("测试名称", test_function_name),
    # ...
]
```

### 测试命名约定

- 函数名: `test_<module>_<aspect>()`
- 示例: `test_parser_agent_structure()`, `test_ppa_estimator_logic()`

### 输出格式

使用统一的输出格式：
```python
print("=" * 70)
print(f"测试 {index}: {name}")
print("=" * 70)
print()
# ... 测试逻辑 ...
print(f"✅ {name} 测试通过")
```

## 持续集成

### CI 集成建议

在 CI 流程中添加：
```yaml
- name: Run Unit Tests
   run: docker compose exec -T agent-core python3 app/dev_tests/run_pre_manager_unit_basic.py
```

### 退出码

- 成功: `exit(0)` - 所有测试通过
- 失败: `exit(1)` - 至少1个测试失败

## 相关文档

- [State Schema 规范](../architecture/state-schema.md)
- [端口与层次结构](../spec/ports-and-hierarchy.md)
- [PPA 报告格式](../ppa/report-format.md)
- [RAG 知识库配置](../rag/knowledge-base.md)
- [Docker 部署指南](../deploy/docker-compose.md)
- [TestAgent 阶段测试报告（2026-03-04）](./TEST_RESULTS_2026-03-04.md)

## 版本历史

- **2024-02-14**: 初始版本，8个单元测试，无 LLM 依赖设计
- **2026-02-22**: 增加 Manager Agent 静态编排测试，更新为9个单元测试
- **2026-03-04**: 增加 TestAgent Docker 集成测试，支持 Verilator/pyuvm 非静态执行与覆盖率回写
- 测试覆盖: State Schema, Preprocessor, PPA Estimator, RAG, Parser Agent, Architect Agent, Workflow, Manager Agent, File Structure
