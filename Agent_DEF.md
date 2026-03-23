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