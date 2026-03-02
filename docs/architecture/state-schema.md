# LangGraph State Schema（完整规范）

本规范定义整个工作流的 `state` 结构，从预处理到架构设计到生成验证的完整状态模型。

## 顶层字段（完整版本）

| 字段 | 类型 | 说明 | 写入阶段 |
| --- | --- | --- | --- |
| intent | object | 设计意图，见 docs/spec/design-intent.md | Parser Agent |
| constraints | object | 结构化约束集合（硬/软） | Parser Agent |
| metadata | object | 请求元数据（时间戳、请求ID等） | Parser Agent |
| architecture | object | 模块层次结构与端口规范 | Architect Agent |
| ast_extraction | object | AST 提取结果（可选，基于已有 HDL） | Architect Agent |
| architecture_validation | object | 架构图验证结果（循环依赖/深度/孤立模块） | Architect Agent/Manager |
| ppa | object | PPA 评估结果与目标 | PPA Estimator |
| coverage | object | 覆盖率结果与阈值 | Coverage Analyzer |
| errors | list | 结构化错误报告 | Analyzer |
| retry_count | dict | 各模块重试计数 | Manager/GenAgent |
| loop_budget | object | 迭代预算控制 | Manager |
| versions | list | 版本迭代记录 | Architect/Manager |
| modules | dict | 模块生成状态与代码路径 | GenAgent |
| tests | dict | 测试用例生成状态 | TestAgent |
| manager | object | Manager 编排摘要（下一模块/计划/状态） | Manager |

## 字段详细定义

### 1. intent（设计意图）

预处理阶段输出，详细定义见 [docs/spec/design-intent.md](../spec/design-intent.md)

```json
{
  "summary": "实现一个带AXI-Lite接口的寄存器文件",
  "target_language": "verilog",
  "clock": "clk",
  "reset": "rst_n",
  "interfaces": ["axi-lite"]
}
```

### 2. constraints（约束条件）

```json
{
  "hard": [
    {"name": "freq", "value": "200MHz", "priority": 0},
    {"name": "data_width", "value": 32, "priority": 0}
  ],
  "soft": [
    {"name": "area", "value": "minimize", "priority": 1},
    {"name": "power", "value": "low", "priority": 2}
  ]
}
```

### 3. metadata（元数据）

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-02-14T10:30:00+08:00",
  "language": "zh",
  "source": "tui",
  "workflow_version": "v1.0"
}
```

### 4. architecture（架构设计）

由 Architect Agent 生成，详细规范见 [docs/spec/ports-and-hierarchy.md](../spec/ports-and-hierarchy.md)

```json
{
  "version": 1,
  "hierarchy": {
    "top": {
      "name": "axis_register_file",
      "type": "top",
      "children": ["axi_slave", "reg_array"],
      "ports": {
        "clk": {"type": "input", "width": 1},
        "rst_n": {"type": "input", "width": 1},
        "s_axi_*": {"type": "axi_slave", "protocol": "AXI4-Lite"}
      }
    },
    "modules": [
      {
        "name": "axi_slave",
        "type": "leaf",
        "description": "AXI-Lite 从设备接口",
        "ports": {...}
      },
      {
        "name": "reg_array",
        "type": "leaf",
        "description": "寄存器阵列存储",
        "ports": {...}
      }
    ]
  },
  "interfaces": [
    {
      "name": "s_axi",
      "protocol": "AXI4-Lite",
      "mode": "slave",
      "data_width": 32,
      "addr_width": 12
    }
  ]
}
```

### 5. ppa（性能功耗面积评估）

由 PPA Estimator 生成，详细格式见 [docs/ppa/report-format.md](../ppa/report-format.md)

```json
{
  "version": 1,
  "estimated_at": "2026-02-14T10:31:00+08:00",
  "area": {
    "total_gates": 5000,
    "registers": 128,
    "combinational": 4872,
    "unit": "gate_equivalents"
  },
  "power": {
    "dynamic_mw": 12.5,
    "static_mw": 0.8,
    "total_mw": 13.3,
    "voltage": 1.2
  },
  "timing": {
    "max_freq_mhz": 250,
    "critical_path_ns": 4.0,
    "setup_margin_ns": 0.5
  },
  "feasibility": "high",
  "warnings": []
}
```

### 5a. ast_extraction（AST提取结果，可选）

用于“基于已有 HDL 迭代设计”场景，记录 AST 提取出的结构化信息。

```json
{
  "source_files": [
    "workspace/hierarchy/top/design_top.v"
  ],
  "modules": [
    {
      "name": "design_top",
      "ports": ["clk", "rst_n", "s_axi_awaddr"],
      "parameters": ["DATA_WIDTH", "ADDR_WIDTH"],
      "instances": ["axi_slave", "reg_array"]
    }
  ],
  "features": {
    "interface_types": ["axi4-lite"],
    "hierarchy_depth": 2,
    "is_parameterized": true
  },
  "status": "success",
  "errors": []
}
```

### 5b. architecture_validation（架构图验证）

对 `architecture.hierarchy` 执行图论验证，避免将 AST 用于 JSON 一致性校验。

> 版本说明：当前版本不实现图结构测试与非静态测试；上述验证结构作为下一版本落地目标保留。下一版本实现时，结构化解析与验证输入仍采用 AST 方法，不使用 Regex 做语义解析。

```json
{
  "graph_checks": {
    "has_cycle": false,
    "max_depth": 2,
    "orphan_modules": [],
    "unresolved_references": []
  },
  "status": "pass",
  "warnings": [],
  "checked_at": "2026-02-22T10:40:00+08:00"
}
```

### 6. coverage（覆盖率）

由 Coverage Analyzer 填写

```json
{
  "code_coverage": {
    "line": 96.5,
    "branch": 92.3,
    "fsm_state": 100.0
  },
  "functional_coverage": {
    "interface_protocol": 95.0,
    "data_patterns": 88.0,
    "corner_cases": 85.0
  },
  "assertion_coverage": {
    "total_assertions": 25,
    "covered": 24,
    "percentage": 96.0
  },
  "thresholds": {
    "code_min": 95.0,
    "functional_min": 90.0
  },
  "status": "pass"
}
```

### 7. errors（错误报告）

结构化错误列表，详细格式见 [docs/testing/error-report.md](../testing/error-report.md)

```json
[
  {
    "module": "axi_slave",
    "type": "syntax_error",
    "severity": "error",
    "message": "Syntax error at line 45: missing semicolon",
    "file": "workspace/hierarchy/leaf/axi_slave.v",
    "line": 45,
    "column": 12,
    "suggestion": "Add ';' after statement"
  }
]
```

### 8. retry_count（重试计数）

按模块记录重试次数

```json
{
  "axi_slave": 1,
  "reg_array": 0,
  "global": 1
}
```

### 9. loop_budget（迭代预算）

控制自动优化的迭代次数

```json
{
  "max_iterations": 10,
  "current_iteration": 3,
  "remaining": 7,
  "auto_optimize": true,
  "stop_on_no_improvement": true,
  "no_improvement_threshold": 2
}
```

### 10. versions（版本记录）

记录架构演进历史

```json
[
  {
    "version": 1,
    "timestamp": "2026-02-14T10:31:00+08:00",
    "changes": "初始架构设计",
    "ppa_snapshot": {...},
    "coverage_snapshot": null,
    "status": "baseline"
  },
  {
    "version": 2,
    "timestamp": "2026-02-14T10:45:00+08:00",
    "changes": "增加流水线寄存器以提升频率",
    "ppa_snapshot": {...},
    "coverage_snapshot": {...},
    "status": "improved",
    "improvement": "+15% freq, +2% area"
  }
]
```

### 11. modules（模块生成状态）

由 GenAgent 填写

```json
{
  "axi_slave": {
    "status": "completed",
    "file_path": "workspace/hierarchy/leaf/axi_slave.v",
    "generated_at": "2026-02-14T10:50:00+08:00",
    "lines_of_code": 235,
    "retry_count": 0
  },
  "reg_array": {
    "status": "in_progress",
    "file_path": null,
    "generated_at": null
  }
}
```

### 12. tests（测试状态）

由 TestAgent 填写

```json
{
  "axi_slave": {
    "status": "completed",
    "test_file": "workspace/testbench/unit/tb_axi_slave.py",
    "framework": "cocotb",
    "test_cases": 15
  }
}
```

### 13. manager（编排摘要）

由 Manager Agent 填写，用于记录当前编排状态与下一步动作。

```json
{
  "status": "ready_for_generation",
  "next_module": "axi_slave",
  "execution_plan": ["axi_slave", "reg_array", "axi_register_file"],
  "updated_at": "2026-02-22T12:10:00+08:00",
  "version_scope": "static_only_v1"
}
```

## TypedDict 定义（Python）

完整的 State Schema 在代码中定义为：

```python
from typing import TypedDict, List, Dict, Any, Optional

class AGVSState(TypedDict, total=False):
    """Complete LangGraph State for AGVS4RTL workflow."""
    
    # Pre-processing stage
    intent: Dict[str, Any]
    constraints: Dict[str, List[Dict[str, Any]]]
    metadata: Dict[str, Any]
    
    # Architecture stage
    architecture: Dict[str, Any]
    ast_extraction: Dict[str, Any]
    architecture_validation: Dict[str, Any]
    ppa: Dict[str, Any]
    
    # Verification stage
    coverage: Dict[str, Any]
    errors: List[Dict[str, Any]]
    
    # Control & versioning
    retry_count: Dict[str, int]
    loop_budget: Dict[str, Any]
    versions: List[Dict[str, Any]]
    
    # Generation stage
    modules: Dict[str, Dict[str, Any]]
    tests: Dict[str, Dict[str, Any]]
    manager: Dict[str, Any]
```

## 相关规范文档

- [设计意图规范](../spec/design-intent.md)
- [端口与层次结构规范](../spec/ports-and-hierarchy.md)
- [PPA 报告格式](../ppa/report-format.md)
- [覆盖率报告格式](../testing/coverage-report.md)
- [错误报告格式](../testing/error-report.md)
- [Agent 配置规范](../spec/agent-config.md)
