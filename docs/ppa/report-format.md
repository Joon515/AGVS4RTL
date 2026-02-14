# PPA 报告格式规范

本规范定义 PPA（Performance, Power, Area）评估报告的 JSON 格式，用于架构阶段的可行性分析与版本对比。

## 报告结构

```json
{
  "version": 1,
  "estimated_at": "2026-02-14T10:31:00+08:00",
  "estimator": "rule_based_v1",
  "area": {...},
  "power": {...},
  "timing": {...},
  "feasibility": "high|medium|low",
  "warnings": [],
  "metadata": {...}
}
```

## 字段详细定义

### 1. 顶层元数据

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | integer | 报告格式版本号 |
| `estimated_at` | string | 评估时间戳（ISO 8601） |
| `estimator` | string | 评估引擎版本（如 `rule_based_v1`, `ml_model_v2`） |
| `feasibility` | enum | 可行性评级：`high`、`medium`、`low` |
| `warnings` | array | 警告信息列表 |

### 2. area（面积）

基于门当量（Gate Equivalents, GE）或逻辑单元（LUTs/FFs）估算。

```json
{
  "area": {
    "total_gates": 5000,
    "breakdown": {
      "registers": 128,
      "combinational": 4872,
      "memory_bits": 32768
    },
    "unit": "gate_equivalents",
    "technology": "28nm",
    "utilization": {
      "estimated_area_mm2": 0.05,
      "fpga_luts": 1200,
      "fpga_ffs": 800
    }
  }
}
```

#### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `total_gates` | integer | 总门数（ASIC）或等效逻辑资源 |
| `breakdown.registers` | integer | 寄存器数量（FF） |
| `breakdown.combinational` | integer | 组合逻辑门数 |
| `breakdown.memory_bits` | integer | 存储器位宽（BRAM/SRAM） |
| `unit` | string | 计量单位：`gate_equivalents`、`luts`、`slices` |
| `technology` | string | 工艺节点（如 `28nm`、`7nm`）或 FPGA 型号 |
| `utilization.estimated_area_mm2` | float | ASIC 面积估算（mm²） |
| `utilization.fpga_luts` | integer | FPGA LUT 使用量 |
| `utilization.fpga_ffs` | integer | FPGA 触发器使用量 |

### 3. power（功耗）

单位为毫瓦（mW）。

```json
{
  "power": {
    "dynamic_mw": 12.5,
    "static_mw": 0.8,
    "total_mw": 13.3,
    "voltage": 1.2,
    "breakdown": {
      "clock_tree_mw": 3.2,
      "logic_mw": 6.8,
      "io_mw": 2.5,
      "leakage_mw": 0.8
    },
    "conditions": {
      "temperature_c": 25,
      "activity_factor": 0.2
    }
  }
}
```

#### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `dynamic_mw` | float | 动态功耗（开关功耗） |
| `static_mw` | float | 静态功耗（漏电流） |
| `total_mw` | float | 总功耗 = 动态 + 静态 |
| `voltage` | float | 工作电压（V） |
| `breakdown.clock_tree_mw` | float | 时钟树功耗 |
| `breakdown.logic_mw` | float | 逻辑开关功耗 |
| `breakdown.io_mw` | float | I/O 接口功耗 |
| `breakdown.leakage_mw` | float | 漏电功耗 |
| `conditions.temperature_c` | float | 工作温度（℃） |
| `conditions.activity_factor` | float | 平均翻转率（0-1） |

### 4. timing（时序）

```json
{
  "timing": {
    "max_freq_mhz": 250,
    "min_period_ns": 4.0,
    "critical_path": {
      "delay_ns": 3.5,
      "slack_ns": 0.5,
      "startpoint": "reg_array/data_reg[0]",
      "endpoint": "axi_slave/rdata_reg[31]",
      "logic_levels": 5
    },
    "clock_domains": [
      {
        "name": "clk_axi",
        "frequency_mhz": 200,
        "period_ns": 5.0
      }
    ],
    "constraints": {
      "input_delay_ns": 1.0,
      "output_delay_ns": 1.5,
      "clock_uncertainty_ns": 0.3
    }
  }
}
```

#### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `max_freq_mhz` | float | 最大工作频率（MHz） |
| `min_period_ns` | float | 最小时钟周期（ns） |
| `critical_path.delay_ns` | float | 关键路径延迟 |
| `critical_path.slack_ns` | float | 时序裕量（正值表示满足约束） |
| `critical_path.startpoint` | string | 起点寄存器 |
| `critical_path.endpoint` | string | 终点寄存器 |
| `critical_path.logic_levels` | integer | 组合逻辑级数 |
| `clock_domains` | array | 时钟域列表 |
| `constraints` | object | 时序约束参数 |

### 5. feasibility（可行性评级）

基于 PPA 综合评估确定：

| 评级 | 条件 | 说明 |
|------|------|------|
| `high` | 所有指标在目标范围内 | 可直接实现 |
| `medium` | 1-2 个指标接近边界 | 需小幅优化 |
| `low` | 多个指标超出约束 | 需重构架构 |

### 6. warnings（警告信息）

```json
{
  "warnings": [
    {
      "severity": "warning",
      "category": "timing",
      "message": "时钟频率接近工艺极限，建议增加流水线级数",
      "affected_modules": ["axi_slave"]
    },
    {
      "severity": "info",
      "category": "power",
      "message": "时钟树功耗占比较高（24%），考虑时钟门控",
      "affected_modules": ["top"]
    }
  ]
}
```

#### 警告级别

| severity | 说明 |
|----------|------|
| `error` | 无法实现，必须修改 |
| `warning` | 建议优化 |
| `info` | 提示信息 |

### 7. metadata（附加信息）

```json
{
  "metadata": {
    "architecture_version": 1,
    "constraint_summary": {
      "freq_target_mhz": 200,
      "area_budget_gates": 10000,
      "power_budget_mw": 20
    },
    "estimation_method": "analytical",
    "confidence": 0.75
  }
}
```

## 完整示例

```json
{
  "version": 1,
  "estimated_at": "2026-02-14T10:31:00+08:00",
  "estimator": "rule_based_v1",
  "area": {
    "total_gates": 5000,
    "breakdown": {
      "registers": 128,
      "combinational": 4872,
      "memory_bits": 32768
    },
    "unit": "gate_equivalents",
    "technology": "28nm",
    "utilization": {
      "estimated_area_mm2": 0.05,
      "fpga_luts": 1200,
      "fpga_ffs": 800
    }
  },
  "power": {
    "dynamic_mw": 12.5,
    "static_mw": 0.8,
    "total_mw": 13.3,
    "voltage": 1.2,
    "breakdown": {
      "clock_tree_mw": 3.2,
      "logic_mw": 6.8,
      "io_mw": 2.5,
      "leakage_mw": 0.8
    },
    "conditions": {
      "temperature_c": 25,
      "activity_factor": 0.2
    }
  },
  "timing": {
    "max_freq_mhz": 250,
    "min_period_ns": 4.0,
    "critical_path": {
      "delay_ns": 3.5,
      "slack_ns": 0.5,
      "startpoint": "reg_array/data_reg[0]",
      "endpoint": "axi_slave/rdata_reg[31]",
      "logic_levels": 5
    },
    "clock_domains": [
      {
        "name": "clk_axi",
        "frequency_mhz": 200,
        "period_ns": 5.0
      }
    ],
    "constraints": {
      "input_delay_ns": 1.0,
      "output_delay_ns": 1.5,
      "clock_uncertainty_ns": 0.3
    }
  },
  "feasibility": "high",
  "warnings": [],
  "metadata": {
    "architecture_version": 1,
    "constraint_summary": {
      "freq_target_mhz": 200,
      "area_budget_gates": 10000,
      "power_budget_mw": 20
    },
    "estimation_method": "analytical",
    "confidence": 0.75
  }
}
```

## 版本对比

在迭代优化时，使用差异对比格式：

```json
{
  "comparison": {
    "baseline_version": 1,
    "current_version": 2,
    "changes": {
      "area": {
        "delta_gates": 120,
        "delta_percent": 2.4,
        "trend": "increase"
      },
      "power": {
        "delta_mw": -1.2,
        "delta_percent": -9.0,
        "trend": "decrease"
      },
      "timing": {
        "delta_freq_mhz": 30,
        "delta_percent": 12.0,
        "trend": "increase"
      }
    },
    "overall_improvement": true,
    "reason": "增加流水线寄存器，频率提升12%，面积增加仅2.4%"
  }
}
```

## 相关文档

- [LangGraph State Schema](../architecture/state-schema.md)
- [端口与层次结构规范](../spec/ports-and-hierarchy.md)
- [设计意图规范](../spec/design-intent.md)
