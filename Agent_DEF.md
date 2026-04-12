以下是对 **Parser 模块** 行为的技术定义：

---

### 1. I/O 行为：任务初始化与持久化
这是工作流的“冷启动”阶段。
* **UUID 分配**：调用 `generate_global_task_id()`。
* **目录结构规范**：
    ```text
    /Output
      └── /TASK_20260324_8a2b3c4d  <-- 全局唯一 TaskID
          ├── /Origin              <-- 原始需求文档 (.txt, .pdf, .v)
          ├── /UserTaskSpec.json   <-- Parser 产出的结构化规约
          └── /Archive             <-- (最终存档区)
    ```
* **操作**：Parser 接收到请求后，第一时间同步创建物理目录，将原始输入落盘。

---

### 2. 读取后：语义路由与规约生成
这是 Parser 的“大脑”功能，核心是将非结构化文本转化为结构化 Pydantic 模型。
* **UserTaskSpec 实例化**：利用 LLM 提取关键字段（如 `top_module`, `intent`, `design_rules`）。
* **语义路由 (Semantic Router)**：
    * **过滤层**：识别是否包含非法请求或超出能力的范围。
    * **决策层**：判定 `IntentCategory`。例如，用户提到“修复”，路由至 `FIX_BUG`；提到“新模块”，路由至 `GEN_WITH_TEST`。
* **任务队列**：将实例化的 `WorkTaskPayload` 推送至任务总线（Fast
API）。

---

### 3. 文件管理：共享工作区 (Sandbox) 策略
为了保证 Gen（生成）和 Verify（验证）模块能在一个干净的环境下工作：
* **环境隔离**：将 `/Origin` 中的参考代码或文档复制到 `/SharedWorkspace/TASK_ID/`。
* **轻量化通信**：不通过 API 发送整个 JSON 字符串，而是将 `UserTaskSpec` 序列化为文件，仅在模块间传递 **`spec_file_path`** 和 **`iteration`** 计数器。
* **幂等性**：`iteration`决定 Gen 模块是“从零开始”还是“基于上一轮结果增量修改”。

---

### 4. 模块通信：状态机与大文件规避
* **控制面 (Control Plane)**：模块间回传 `WorkflowTraceStep`。包含 `status` (success/error) 和 `detail`。
* **数据面 (Data Plane)**：模块不返回 RTL 代码字符串，而是返回 `rtl_path` 或 `sim_log_path`。
* **Parser 的角色**：Parser 此时充当 **Orchestrator（编排器）**。它读取 `VerifyNodeOutput.report.verdict`，如果失败，则根据 `error_details` 决定是否发起下一轮 `iteration`。



---

### 5. 结束存档：清理与归档
* **原子化操作**：任务完成（PASS）或达到最大重试轮次（FAIL）后，触发归档。
* **Archive 动作**：将 `/SharedWorkspace` 中产生的所有中间产物（生成的 Verilog、波形文件 .vcd、日志）搬运回 `/Output/TASK_ID/Result`。
* **空间回收**：`rm -rf /SharedWorkspace/TASK_ID`。

---

以下是对 **Gen (Generator) 模块** 行为的技术定义：

### 6. I/O 行为：内部服务与通信层
这是 Gen 模块接收任务与回传产物的物理边界。
* **网络隔离**：基于 FastAPI 构建，仅在 Docker 容器内部网络中提供 API 接口服务，不对外开放端口，保障系统安全性。
* **输入接收**：接收来自 Parser 的任务载荷，解析并读取前置依赖，如 `TaskSpec` 以及（在重试迭代中的）`VerifyRpt` 验证报告。
* **输出发射**：遵循轻量化通信协议，发送 `SpecReg` 的文件路径和 RTL 生成代码的路径给编排器，不直接通过 HTTP 传递大规模文本或代码串。

### 7. 核心逻辑：多轮对话与 RTL 生成
Gen 模块在系统中扮演“架构师 + 程序员”的双重角色。
* **工作区访问**：直接挂载并访问 `/SharedWorkspace/TASK_ID/` 目录，从中读取原始参考文档、旧版本代码块等上下文信息。
* **多轮对话逻辑**：维护多轮交互上下文。当 `iteration > 0` 时，Gen 模块会根据 Verify 模块提供的 `VerifyRpt`（错误日志、波形反馈等）进行对齐和反思，驱动大模型对原有代码进行增量修复。
* **代码生成**：生成符合语法规范和设计意图的 Verilog 代码，并自动将产物落盘到共享工作区的 `/rtl` 子目录下。

### 8. 规约抽象：SpecReg (规格注册表)
为了在多 Agent 协同中消除大模型的“幻觉”与接口不匹配问题。
* **文档定义**：`SpecReg` 是一份在内部维护的增量、只读文档，它是对原始 `TaskSpec` 的技术具象化。
* **核心内容**：`SpecReg` 内部维护**类图架构逻辑**。
    * **图结构特征**：类图架构逻辑特指多轮对话生成的 Verilog 模块逻辑。因为 Verilog 模块是不同于常规软件代码树状结构的**图结构**（视模块内部逻辑或子模块为节点，端口连线为边）。
    * **渐进式细化**：我们在逐次对话中逐步细化 Verilog 模块图的节点，不断拆解和具象化，直到该节点被完全实现为纯组合逻辑（或基础时序逻辑）为止。
* **消费端**：`SpecReg` 存放于共享工作区，不仅指导当前迭代的代码生成，后续也将作为契约供 Verify 模块执行静态语法与动态语义的核查。