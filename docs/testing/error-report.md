# 错误报告格式（testing）

本文档定义测试阶段的结构化错误报告 JSON。

## 版本范围说明

- 当前版本：定义错误格式与分类，支持静态阶段回写。
- 下一版本：对接非静态测试与图结构测试的真实错误来源。
- 方法边界：结构化语义来源保持 AST，不使用 Regex 作为模块层次/端口语义主解析手段。

## JSON Schema（建议）

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
    "suggestion": "Add ';' after statement",
    "source": "verilator"
  }
]
```

## 错误类型

- `syntax_error`: 语法错误（当前重试策略可不计次）
- `functional_error`: 功能错误（计入模块重试）
- `timing_violation`: 时序违规（计入模块重试）
- `environment_error`: 环境或执行错误（按策略处理）

## 状态回写建议

- 回写路径：`state.errors`
- 重试映射：`ManagerAgent` 根据 `type` 写回 `state.retry_count`
