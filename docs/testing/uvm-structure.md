# UVM 测试结构与模板（testing）

本文档定义 pyuvm/cocotb 侧的测试层次结构与模板约束。

## 版本范围说明

- 当前版本：规范定义与模板约束，不实现非静态执行链路。
- 下一版本：接入真实非静态测试流程与图结构测试执行。
- 方法边界：测试上下文中的结构化设计信息来源保持 AST，不使用 Regex 做模块层次/端口语义解析。

## 结构映射

- `uvm_test`：测试场景入口
- `uvm_env`：验证环境容器
- `uvm_agent`：接口代理
- `uvm_sequencer`：激励序列控制
- `uvm_scoreboard`：参考模型比对
- `uvm_coverage`：覆盖率采集

## 目录建议

```text
workspace/testbench/
  unit/
  integration/
  common/
```

## 模板字段（建议）

```json
{
  "module": "axi_slave",
  "interfaces": ["AXI4-Lite"],
  "clock": "clk",
  "reset": "rst_n",
  "test_types": ["smoke", "corner", "error_injection"],
  "coverage_targets": {
    "code_min": 95,
    "functional_min": 90
  }
}
```

## 状态回写建议

- 生成状态：`state.tests`
- 覆盖率状态：`state.coverage`
- 错误状态：`state.errors`
