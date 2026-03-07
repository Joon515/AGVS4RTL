# 覆盖率报告格式（testing）

本文档定义测试阶段的覆盖率 JSON 结构与字段语义。

## 版本范围说明

- 当前版本：已实现模块级非静态测试与覆盖率产物接入。
- 下一版本：补齐图结构覆盖率与断言覆盖率自动采集。
- 方法边界：结构化上下文与验证输入继续采用 AST，不使用 Regex 进行模块层次与端口语义解析。

## JSON Schema（建议）

```json
{
  "version": "v1",
  "generated_at": "2026-02-22T12:00:00+08:00",
  "status": "pass",
  "thresholds": {
    "code_min": 95.0,
    "functional_min": 90.0
  },
  "reports": [
    {
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
      "status": "pass",
      "notes": []
    }
  ],
  "notes": [
    "Module-level simulation executed via sandbox when available"
  ]
}
```

## 产物来源（当前实现）

1. Verilator 编译参数：`--coverage --coverage-line --coverage-toggle`
2. 仿真产物：`coverage.dat`
3. 转换命令：`verilator_coverage --write-info <module>.info coverage.dat`
4. 解析规则：
   - `DA:` 统计行覆盖率
   - `BRDA:` 统计分支覆盖率
   - `*_results.xml` 解析功能测试通过率（映射为 `functional_coverage`）

## 字段约束

- 顶层 `status`: `pass` | `fail` | `pending`
- 模块级 `reports[].status`: `pass` | `fail` | `pending`
- 覆盖率字段均为 0~100 的浮点数
- `thresholds` 为判定阈值，Analyzer 使用统一判定规则

## 状态回写建议

- 回写路径：`state.coverage`
- 同步记录：`state.versions[].coverage_snapshot`
