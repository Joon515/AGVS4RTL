# 覆盖率报告格式（testing）

本文档定义测试阶段的覆盖率 JSON 结构与字段语义。

## 版本范围说明

- 当前版本：仅定义报告格式与静态字段约束。
- 下一版本：实现非静态测试与图结构测试产物接入。
- 方法边界：结构化上下文与验证输入继续采用 AST，不使用 Regex 进行模块层次与端口语义解析。

## JSON Schema（建议）

```json
{
  "version": "v1",
  "generated_at": "2026-02-22T12:00:00+08:00",
  "module": "axi_slave",
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
  "status": "pass",
  "notes": []
}
```

## 字段约束

- `status`: `pass` | `fail`
- 覆盖率字段均为 0~100 的浮点数
- `thresholds` 为判定阈值，Analyzer 使用统一判定规则

## 状态回写建议

- 回写路径：`state.coverage`
- 同步记录：`state.versions[].coverage_snapshot`
