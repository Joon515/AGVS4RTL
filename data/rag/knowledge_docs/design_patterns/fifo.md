---
title: "FIFO (先进先出队列) 设计模式"
category: "design_patterns"
tags: ["fifo", "queue", "buffer", "flow-control"]
complexity: "medium"
hdl_language: ["verilog", "systemverilog"]
ppa_profile:
  area_gates: 500
  max_freq_mhz: 400
  power_mw: 3.5
last_updated: "2026-02-14"
---

# FIFO (First-In-First-Out) 设计模式

## 概述
FIFO是数字设计中最常用的缓冲结构，用于在不同速率或时钟域之间传递数据。它保证数据按写入顺序读出，提供流量控制机制。

## 应用场景
- **时钟域交叉** (Clock Domain Crossing, CDC)
- **速率匹配** (Rate Matching)
- **数据缓冲** (Data Buffering)
- **异步接口** (Asynchronous Interface)

## FIFO类型

### 1. 同步FIFO (Synchronous FIFO)
- 读写共用同一个时钟
- 结构简单，延迟低
- 适用于同时钟域的速率匹配

### 2. 异步FIFO (Asynchronous FIFO)
- 读写使用独立时钟
- 需要格雷码指针同步
- 适用于CDC场景

## 模块端口定义

```verilog
module sync_fifo #(
    parameter DATA_WIDTH = 32,
    parameter FIFO_DEPTH = 16,  // Must be power of 2
    parameter ADDR_WIDTH = $clog2(FIFO_DEPTH)
) (
    input  wire                  clk,
    input  wire                  rst_n,
    
    // Write Interface
    input  wire [DATA_WIDTH-1:0] wr_data,
    input  wire                  wr_en,
    output wire                  full,
    output wire                  almost_full,  // Programmable threshold
    
    // Read Interface
    output wire [DATA_WIDTH-1:0] rd_data,
    input  wire                  rd_en,
    output wire                  empty,
    output wire                  almost_empty,
    
    // Status
    output wire [ADDR_WIDTH:0]   count  // Current data count (0 to DEPTH)
);
```

## 核心设计要素

### 1. 存储阵列
```verilog
reg [DATA_WIDTH-1:0] fifo_mem [0:FIFO_DEPTH-1];
```

### 2. 读写指针
```verilog
reg [ADDR_WIDTH:0] wr_ptr;  // N+1 bits to distinguish full/empty
reg [ADDR_WIDTH:0] rd_ptr;
```

**为什么用N+1位？**
- N位指针无法区分空（ptr相等）和满（ptr相等但绕了一圈）
- N+1位指针的MSB用于判断绕圈

### 3. 满空判断逻辑
```verilog
assign full  = (wr_ptr[ADDR_WIDTH] != rd_ptr[ADDR_WIDTH]) &&
               (wr_ptr[ADDR_WIDTH-1:0] == rd_ptr[ADDR_WIDTH-1:0]);

assign empty = (wr_ptr == rd_ptr);
```

### 4. 几乎满/空标志
```verilog
parameter ALMOST_FULL_THRESHOLD  = FIFO_DEPTH - 4;  // Programmable
parameter ALMOST_EMPTY_THRESHOLD = 4;

assign almost_full  = (count >= ALMOST_FULL_THRESHOLD);
assign almost_empty = (count <= ALMOST_EMPTY_THRESHOLD);
```

### 5. 数据计数
```verilog
assign count = (wr_ptr[ADDR_WIDTH] == rd_ptr[ADDR_WIDTH]) ?
               (wr_ptr[ADDR_WIDTH-1:0] - rd_ptr[ADDR_WIDTH-1:0]) :
               (FIFO_DEPTH - rd_ptr[ADDR_WIDTH-1:0] + wr_ptr[ADDR_WIDTH-1:0]);
```

## 写操作时序

```verilog
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        wr_ptr <= 0;
    end else if (wr_en && !full) begin
        fifo_mem[wr_ptr[ADDR_WIDTH-1:0]] <= wr_data;
        wr_ptr <= wr_ptr + 1;
    end
end
```

## 读操作时序

```verilog
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        rd_ptr <= 0;
    end else if (rd_en && !empty) begin
        rd_ptr <= rd_ptr + 1;
    end
end

assign rd_data = fifo_mem[rd_ptr[ADDR_WIDTH-1:0]];
```

## PPA 特性

### 面积估算（DEPTH=16, WIDTH=32）
- **存储器**: 16 × 32 = 512 bits
- **指针寄存器**: 2 × 5 = 10 FFs
- **控制逻辑**: ~100 GE
- **总计**: ~650 GE + 512-bit SRAM

### 频率估算
- **同步FIFO**: 可达 400 MHz @ 28nm
- **关键路径**: 空/满判断 + 指针更新 (2-3 logic levels)
- **优化**: 可流水线化指针比较逻辑

### 功耗估算
- **动态功耗**: ~3.5 mW @ 200MHz, 50% full rate
- **存储器占主导**: 读写操作产生大量翻转
- **优化**: 使用时钟门控在空闲时关闭存储器

## 设计要点

### ✅ 最佳实践
1. **深度为2的幂**: 简化指针算术，无需模运算
2. **防溢出保护**: 写入时检查`full`，读取时检查`empty`
3. **复位策略**: 仅需复位指针，无需清空存储器
4. **几乎满标志**: 提前通知上游停止写入，避免溢出

### ⚠️ 常见陷阱
1. **指针位宽错误**: 使用N位无法区分满空状态
2. **同时读写**: 在满或空的边界条件下需仔细处理
3. **亚稳态风险**: 异步FIFO必须使用格雷码和双级同步

### 💡 高级优化

#### Show-Ahead模式
```verilog
// 读数据直接从存储器输出，无需等待rd_en
assign rd_data = fifo_mem[rd_ptr[ADDR_WIDTH-1:0]];

// 读指针在rd_en时更新
always @(posedge clk) begin
    if (rd_en && !empty) begin
        rd_ptr <= rd_ptr + 1;
    end
end
```

#### 流水线读取
```verilog
reg [DATA_WIDTH-1:0] rd_data_reg;

always @(posedge clk) begin
    rd_data_reg <= fifo_mem[rd_ptr[ADDR_WIDTH-1:0]];
end

assign rd_data = rd_data_reg;
```

## 异步FIFO扩展

### 格雷码转换
```verilog
function [ADDR_WIDTH:0] bin_to_gray(input [ADDR_WIDTH:0] bin);
    bin_to_gray = bin ^ (bin >> 1);
endfunction

// Write pointer in gray code
wire [ADDR_WIDTH:0] wr_ptr_gray = bin_to_gray(wr_ptr);
```

### 双级同步器
```verilog
// Synchronize read pointer to write clock domain
reg [ADDR_WIDTH:0] rd_ptr_gray_sync1, rd_ptr_gray_sync2;

always @(posedge wr_clk or negedge wr_rst_n) begin
    if (!wr_rst_n) begin
        rd_ptr_gray_sync1 <= 0;
        rd_ptr_gray_sync2 <= 0;
    end else begin
        rd_ptr_gray_sync1 <= rd_ptr_gray;
        rd_ptr_gray_sync2 <= rd_ptr_gray_sync1;
    end
end
```

## 验证要点
1. **边界测试**: 空→非空、满→非满状态转换
2. **溢出保护**: 在`full=1`时写入无效
3. **下溢保护**: 在`empty=1`时读取返回旧数据
4. **连续读写**: 验证指针正确循环
5. **随机测试**: 使用参考模型对比输出顺序

## 典型集成示例

### 与AXI-Stream集成
```verilog
// Write side: AXI-Stream input
assign wr_data = s_axis_tdata;
assign wr_en   = s_axis_tvalid && !full;
assign s_axis_tready = !full;

// Read side: AXI-Stream output
assign m_axis_tdata  = rd_data;
assign m_axis_tvalid = !empty;
assign rd_en = m_axis_tready && !empty;
```

## 相关资源
- Clifford E. Cummings, "Simulation and Synthesis Techniques for Asynchronous FIFO Design"
- Xilinx XAPP1067: "Asynchronous FIFO in Virtex-II FPGAs"
