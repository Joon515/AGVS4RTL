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

---

以下是对 **Verify 模块** 行为的技术定义：

## 9. I/O 行为：内部验证服务与通信边界

这是 Verify 模块接收任务、执行核查并回传验证结果的物理边界。  
* **网络隔离**：基于 FastAPI 构建，仅在 Docker 容器内部网络中提供 API 接口服务，不对外开放端口，保障验证环境与工具链的安全性。  
* **输入接收**：接收来自 Parser 编排器的验证任务载荷，读取 `spec_file_path` 指向的 SpecReg 文件与 `rtl_path` 指向的待验证 Verilog 源码；必要时可通过共享工作区读取前序迭代产物与原始上下文。  
* **输出发射**：遵循轻量化通信协议，不通过 HTTP 回传完整日志、波形或源码文本，而是返回结构化 `VerifyNodeOutput`，其中包含 `VerifyRpt` 验证报告与可选的日志/波形文件路径。  
* **文件落盘**：验证过程中产生的编译日志、仿真日志、波形文件与验证报告统一写入 `/SharedWorkspace/TASK_ID/sim` 或约定目录，供 Parser 归档与 Generator 后续迭代读取。

## 10. 核心逻辑：分层验证与结果裁决

Verify 模块在系统中扮演“裁判 + 诊断器”的角色。  
它的职责不是修改 RTL，而是基于 SpecReg 契约对当前迭代的 RTL 实现执行分层验证，并输出可供工作流路由与下一轮修复消费的结构化反馈。  
* **上下文装载**：读取并解析当前任务的 SpecReg、RTL 文件以及必要的任务元信息（如 `task_id`、`iteration`、`top_module`），建立本轮验证上下文。  
* **静态契约核查**：优先执行轻量级的静态一致性检查，包括模块名、端口定义、时钟/复位接口、关键约束是否与 SpecReg 一致。若发现接口不匹配、顶层定义缺失或契约违背，则判定为 `FAIL_SEMANTIC`。  
* **编译可行性核查**：在静态核查通过后，调用轻量工具链（如 `iverilog`）执行 Verilog 编译检查。若 RTL 无法通过语法或编译阶段，则判定为 `FAIL_COMPILE`。  
* **动态行为核查**：在后续能力扩展中，Verify 可基于 SpecReg 中的 `functional_requirements`、`corner_cases` 与 `verification_directives` 自动生成或调度测试激励，执行动态仿真。若功能行为不符合契约，则判定为 `FAIL_SIMULATION`。  
* **基础设施异常判定**：若验证工具不可用、路径失效、文件损坏、仿真环境异常或执行超时，则判定为 `INFRA_ERROR` 或 `TIMEOUT`，与设计本身错误区分开。  
* **最终裁决**：若各级检查全部通过，则输出 `PASS`；否则输出最具代表性的失败结论，并附带错误快照与修复建议。

## 11. 规约消费：以 SpecReg 为验证契约

为了保证验证逻辑与生成逻辑解耦，Verify 模块不直接依赖用户原始自然语言，而是以 Generator 产出的 SpecReg 作为主验证契约。  
* **契约中心化**：SpecReg 中定义的模块名、端口、参数、时钟复位、功能要求、边界场景与非法条件，是 Verify 判定 RTL 是否“实现正确”的主要依据。  
* **接口核查依据**：静态验证阶段以 `ports`、`clock_and_reset`、`protocols` 等结构化字段为准，判断 RTL 是否满足接口层约束。  
* **行为验证依据**：动态仿真阶段以 `functional_requirements`、`corner_cases`、`illegal_conditions`、`latency_notes` 与 `verification_directives` 为核心输入，构建测试策略与断言判据。  
* **去自然语言漂移**：通过以 SpecReg 为中心的消费模式，减少 Verify 直接依赖原始需求文本所带来的语义漂移与解释不一致问题。  
* **多轮闭环支撑**：当 iteration > 0 时，Verify 生成的报告将反向作为 Generator 修复的输入之一，使 SpecReg 与 VerifyRpt 共同构成系统闭环中的“契约 + 反馈”双文档机制。

## 12. 错误压缩：结构化报告与修复提示

Verify 模块不仅要判断“是否通过”，还要将底层验证噪声压缩为可供上游消费的结构化诊断结果。  
* **错误分类**：将验证失败归类为接口/语义不匹配、编译错误、仿真断言失败、基础设施异常、超时等不同类别。  
* **错误提炼**：从编译器输出、仿真日志或端口比对结果中提取关键信息，如缺失端口、错误行号、断言名、失败时刻与摘要信息，写入 `ErrorSnapshot`。  
* **修复建议**：基于失败类型生成简短的 `suggested_fix`，用于提示 Generator 是需要“代码级重写”还是“架构级回退重构”。  
* **工作流可路由性**：VerifyRpt 中的 `verdict` 必须足够稳定，使 Parser 可以据此决定：
  * 是否进入成功归档；
  * 是否允许重试；
  * 是否应触发架构级修复或代码级修复；
  * 是否因基础设施错误直接终止流程。  
* **轻量回传**：API 返回时只发送结构化摘要与路径，不直接传输大型日志文件、波形文件或仿真输出全文。

## 13. 文件管理：验证产物目录与版本规则

为了保证多轮迭代下的验证结果可追溯、可复盘、可被 Generator 消费，Verify 模块需要遵守统一的文件落盘约定。  
* **结果目录**：验证相关产物统一写入 `/SharedWorkspace/TASK_ID/sim/`，包括编译日志、仿真日志、波形文件与结构化验证报告。  
* **报告命名**：建议按迭代轮次落盘验证报告，例如 `VerifyRpt_iter0.json`、`VerifyRpt_iter1.json`，与 Generator 侧的 `SpecReg_iterN.json` 保持版本对应关系。  
* **日志命名**：建议按轮次或阶段命名编译/仿真日志，如 `compile_iter0.log`、`sim_iter0.log`，便于后续问题定位。  
* **波形管理**：若启用动态仿真并生成波形文件，建议统一写入 `sim/` 目录，命名中显式包含 iteration，避免多轮结果互相覆盖。  
* **归档协同**：Verify 本身不负责最终归档，仅负责保证文件在共享工作区中可被 Parser 在任务结束时统一搬运到 `Output/TASK_ID/Result` 或 `Archive`。

## 14. 模块通信：与 Parser / Generator 的闭环协作

Verify 模块是完整工作流中的中间裁决节点，其输出将直接影响 Parser 的路由决策与 Generator 的下一轮生成策略。  
* **面向 Parser**：回传 `VerifyNodeOutput`，其中最关键的是 `report.verdict`。Parser 依据该 verdict 决定工作流进入成功归档、失败归档还是下一轮重试。  
* **面向 Generator**：当验证失败且允许重试时，VerifyRpt 中的 `error_details` 与 `suggested_fix` 将作为 Generator 下一轮修复的重要输入。  
* **重构级别提示**：Verify 的失败语义需要足够清晰，使上游可以区分这是：
  * 仅需代码修补的 `CODE_REWRITE`
  * 需要规格/结构调整的 `ARCH_REFACTOR`
  * 或无需重构的 `NONE`  
* **轻控制、重数据分离**：Parser 与 Verify 间仅传递任务元信息与文件路径；实际的大文件（日志、波形、报告）始终通过共享工作区完成协作。  
* **迭代一致性**：Verify 必须以当前 `iteration` 为准执行验证与落盘，确保多轮结果不混淆，并使 Generator 能稳定读取上一轮验证反馈。

## 15. 结束输出：验证结论的最小闭环要求

在当前阶段，Verify 模块的首要目标不是实现完整高级仿真，而是先补齐系统的最小验证闭环，使工作流从“能生成”升级到“能判定”。  
* **最小能力要求**：
  * 检查 SpecReg 文件存在且可解析；
  * 检查 RTL 文件存在且可读取；
  * 执行最小静态契约检查；
  * 可选执行 `iverilog` 编译检查；
  * 生成结构化 `VerifyRpt` 并返回 `VerifyNodeOutput`。  
* **最小闭环意义**：即使暂时不具备完整 testbench 或 cocotb 仿真能力，只要 Verify 能稳定输出 `PASS / FAIL_SEMANTIC / FAIL_COMPILE / INFRA_ERROR` 等判决，系统就已经具备最基础的自动反馈与路由能力。  
* **后续扩展方向**：在最小 Stub 稳定后，再逐步引入动态仿真、断言生成、覆盖率统计与更细粒度的修复建议，使 Verify 从“最小裁判”演进为“完整验证 Agent”。