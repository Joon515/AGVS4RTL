# 端口与层次结构规范

本规范定义模块层次树的结构、模块命名规则、端口命名规范以及时序参数格式。

## 模块层次结构

### 层次类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `top` | 顶层模块 | `axis_register_file` |
| `mid` | 中间层模块（组合子模块） | `axi_interconnect` |
| `leaf` | 叶子模块（不含子模块） | `axi_slave`, `fifo` |
| `ip` | 复用IP（来自IP库） | `xilinx_fifo`, `arm_amba` |

### Hierarchy Tree 结构

```json
{
  "version": 1,
  "hierarchy": {
    "top": {
      "name": "axis_register_file",
      "type": "top",
      "description": "带AXI-Lite接口的寄存器文件",
      "children": ["axi_slave_wrapper", "reg_array"],
      "ports": {
        "clk": {"type": "input", "width": 1, "description": "系统时钟"},
        "rst_n": {"type": "input", "width": 1, "description": "异步低电平复位"},
        "s_axi_*": {"type": "interface", "protocol": "AXI4-Lite"}
      }
    },
    "modules": [
      {
        "name": "axi_slave_wrapper",
        "type": "leaf",
        "description": "AXI4-Lite 从设备接口封装",
        "ports": {...},
        "parameters": {
          "ADDR_WIDTH": 12,
          "DATA_WIDTH": 32
        }
      },
      {
        "name": "reg_array",
        "type": "leaf",
        "description": "寄存器阵列存储（4KB）",
        "ports": {...},
        "parameters": {
          "NUM_REGS": 1024,
          "REG_WIDTH": 32
        }
      }
    ]
  }
}
```

## 模块命名规则

### 命名约定

- **模块名**：小写蛇形命名法 `module_name`
- **顶层模块**：体现功能 + 接口，如 `axi_register_file`、`uart_transceiver`
- **子模块**：功能描述，如 `axi_slave`、`write_channel`、`fifo_controller`
- **IP 模块**：保留原厂前缀，如 `xilinx_bram`、`arm_gic`

### 禁止使用的命名

- 单字符名称（除参数如 `N`）
- 保留字（`input`、`output`、`wire`、`reg` 等）
- 过于泛化的名称（`module1`、`top`、`test`）

## 端口规范

### 端口字段定义

```json
{
  "name": "s_axi_awaddr",
  "type": "input",
  "width": 12,
  "protocol": "AXI4-Lite",
  "description": "写地址通道地址信号",
  "timing": {
    "setup_ns": 0.5,
    "hold_ns": 0.2
  }
}
```

### 端口类型

| 类型 | 说明 |
|------|------|
| `input` | 输入端口 |
| `output` | 输出端口 |
| `inout` | 双向端口 |
| `interface` | 接口束（多个相关信号） |

### 端口命名约定

#### 时钟与复位
- 时钟：`clk`, `clk_<domain>` (如 `clk_axi`, `clk_core`)
- 复位：`rst_n` (低电平有效), `rst` (高电平有效)
- 时钟使能：`clk_en`, `<module>_en`

#### 接口前缀
| 协议 | 前缀 | 示例 |
|------|------|------|
| AXI4-Lite (Slave) | `s_axi_*` | `s_axi_awaddr`, `s_axi_wdata` |
| AXI4-Lite (Master) | `m_axi_*` | `m_axi_araddr`, `m_axi_rdata` |
| APB (Slave) | `s_apb_*` | `s_apb_paddr`, `s_apb_pwrite` |
| AXI-Stream (Input) | `s_axis_*` | `s_axis_tdata`, `s_axis_tvalid` |
| AXI-Stream (Output) | `m_axis_*` | `m_axis_tdata`, `m_axis_tready` |

#### 信号方向后缀
- 有效信号：`_valid`, `_ready`, `_enable`
- 数据信号：`_data`, `_addr`, `_cmd`
- 状态信号：`_done`, `_busy`, `_error`
- 低电平有效：`_n` (如 `rst_n`, `cs_n`)

### 端口宽度表示

```json
{
  "width": 32,              // 固定宽度
  "width": "DATA_WIDTH",    // 参数化宽度
  "width": "ADDR_WIDTH-1:0" // Verilog 风格范围
}
```

## 接口规范

### 接口定义

```json
{
  "name": "s_axi",
  "protocol": "AXI4-Lite",
  "version": "AMBA 3.0",
  "mode": "slave",
  "data_width": 32,
  "addr_width": 12,
  "signals": [
    {"name": "awaddr", "type": "input", "width": 12},
    {"name": "awvalid", "type": "input", "width": 1},
    {"name": "awready", "type": "output", "width": 1},
    {"name": "wdata", "type": "input", "width": 32},
    {"name": "wstrb", "type": "input", "width": 4},
    {"name": "wvalid", "type": "input", "width": 1},
    {"name": "wready", "type": "output", "width": 1},
    {"name": "bresp", "type": "output", "width": 2},
    {"name": "bvalid", "type": "output", "width": 1},
    {"name": "bready", "type": "input", "width": 1},
    {"name": "araddr", "type": "input", "width": 12},
    {"name": "arvalid", "type": "input", "width": 1},
    {"name": "arready", "type": "output", "width": 1},
    {"name": "rdata", "type": "output", "width": 32},
    {"name": "rresp", "type": "output", "width": 2},
    {"name": "rvalid", "type": "output", "width": 1},
    {"name": "rready", "type": "input", "width": 1}
  ]
}
```

### 支持的标准协议

| 协议名 | 用途 | 参考标准 |
|--------|------|----------|
| `AXI4` | 高性能片上互连 | ARM AMBA AXI4 |
| `AXI4-Lite` | 简化版寄存器访问 | ARM AMBA AXI4 |
| `AXI-Stream` | 数据流传输 | ARM AMBA AXI4 |
| `APB` | 低速外设总线 | ARM AMBA APB |
| `Avalon-MM` | Altera 存储映射接口 | Intel Avalon |
| `Wishbone` | 开源片上总线 | OpenCores |

## 时序参数

### 全局时序约束

```json
{
  "clock": {
    "frequency_mhz": 200,
    "period_ns": 5.0,
    "duty_cycle": 0.5
  },
  "reset": {
    "type": "async",
    "polarity": "active_low",
    "duration_cycles": 10
  },
  "timing_constraints": {
    "input_delay_ns": 1.0,
    "output_delay_ns": 1.5,
    "max_path_delay_ns": 4.0
  }
}
```

### 端口级时序

```json
{
  "port": "s_axi_awaddr",
  "timing": {
    "setup_ns": 0.5,
    "hold_ns": 0.2,
    "clock_to_output_ns": 1.2,
    "related_clock": "clk"
  }
}
```

## 参数化设计

### 模块参数

```json
{
  "parameters": {
    "DATA_WIDTH": {
      "type": "integer",
      "default": 32,
      "range": [8, 64],
      "description": "数据总线宽度"
    },
    "ADDR_WIDTH": {
      "type": "integer",
      "default": 12,
      "range": [4, 32],
      "description": "地址总线宽度"
    },
    "FIFO_DEPTH": {
      "type": "integer",
      "default": 16,
      "power_of_2": true,
      "description": "FIFO深度（必须为2的幂）"
    }
  }
}
```

## 验证要点

### 端口完整性检查

- ✅ 所有 input 端口在父模块中有驱动
- ✅ 所有 output 端口在父模块中有连接
- ✅ 时钟域交叉使用同步逻辑
- ✅ 复位信号覆盖所有时序逻辑

### 接口协议验证

- ✅ 握手信号符合协议规范（如 valid/ready）
- ✅ 数据宽度匹配
- ✅ 地址对齐要求符合规范

## 代码生成模板

### Verilog 模块头

```verilog
module axi_slave_wrapper #(
    parameter ADDR_WIDTH = 12,
    parameter DATA_WIDTH = 32
) (
    // Clock and Reset
    input  wire                    clk,
    input  wire                    rst_n,
    
    // AXI4-Lite Slave Interface
    input  wire [ADDR_WIDTH-1:0]   s_axi_awaddr,
    input  wire                    s_axi_awvalid,
    output wire                    s_axi_awready,
    input  wire [DATA_WIDTH-1:0]   s_axi_wdata,
    input  wire [DATA_WIDTH/8-1:0] s_axi_wstrb,
    input  wire                    s_axi_wvalid,
    output wire                    s_axi_wready,
    output wire [1:0]              s_axi_bresp,
    output wire                    s_axi_bvalid,
    input  wire                    s_axi_bready,
    // ... (Read channels)
    
    // Internal Register Interface
    output wire [ADDR_WIDTH-1:0]   reg_addr,
    output wire [DATA_WIDTH-1:0]   reg_wdata,
    output wire                    reg_wen,
    input  wire [DATA_WIDTH-1:0]   reg_rdata,
    output wire                    reg_ren
);
```

## 相关文档

- [设计意图规范](design-intent.md)
- [LangGraph State Schema](../architecture/state-schema.md)
- [PPA 报告格式](../ppa/report-format.md)
