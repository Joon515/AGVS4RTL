# Design Intent 规范

本规范定义预处理阶段输出的设计意图（`intent`）字段格式，用于后续架构与代码生成。

## 字段定义

| 字段 | 类型 | 说明 | 示例 |
| --- | --- | --- | --- |
| summary | string | 需求摘要（保留原始语义） | "实现一个带AXI-Lite接口的寄存器文件" |
| target_language | string | 目标 HDL 语言 | "verilog" |
| clock | string\|null | 时钟信息 | "clk" |
| reset | string\|null | 复位信息 | "rst_n" |
| interfaces | string[] | 接口/总线关键词列表 | ["axi-lite", "apb"] |

## 示例

```json
{
  "summary": "实现一个带AXI-Lite接口的寄存器文件",
  "target_language": "verilog",
  "clock": "clk",
  "reset": "rst_n",
  "interfaces": ["axi-lite"]
}
```
