# AGVS4RTL Remake Project

AGVS4RTL 是一个面向 RTL 自动生成与验证的多 Agent 系统。

---

### 系统架构设计

系统采用基于 FastAPI 的三服务协同架构，Parser 作为统一入口对外提供 API，Generator 与 Verify 仅在容器内部网络中提供服务。

1. **Parser**: 负责意图解析、任务拆解与全局状态编排。
2. **Generator**: 包含 Architect 与 Coding 两个子节点，内部基于 LangGraph 维持局部状态机，将抽象需求按图结构 (Graph) 逐步细化为 RTL 代码实现。
3. **Verify**: 负责执行从静态语义核查到动态仿真的全闭环验证，生成逻辑不依赖验证环境，验证逻辑仅依赖生成的 Spec 契约。
4. **Data Plane**: 基于 `Shared Workspace` 物理挂载项目开发文件，动态配置 Agent 读取权限，实现标准化文件参考。
5. **Container Topology**: 运行时仅保留 `parser`、`gen`、`verify` 三个容器；`parser` 暴露宿主机端口，`gen` 与 `verify` 只通过 Docker 内部网络被访问。

### 技术栈选择

| 维度 | 选型 | 作用 |
| :--- | :--- | :--- |
| **基础运行环境** | Python 3.11 + Docker | 确保跨平台的一致性与隔离性 |
| **包管理** | **pip + requirements.txt** | 使用标准依赖清单，便于环境复现与镜像构建 |
| **任务调度** | **LangGraph + FastAPI** | 基于 LangGraph 原生支持的 Checkpoint 实现状态机，FastAPI 包装服务流转数据 |
| **Agent 编排** | **LangGraph** | 管理网状非线性逻辑，支持 Checkpoint 状态持久化 |
| **意图路由** | **Semantic Router** | 极速语义过滤，降低 LLM 调用开销 |
| **协议约束** | **Pydantic v2** | 定义强类型 JSON 协议，防止跨节点数据漂移 |
| **硬件验证** | **Cocotb + iverilog** | 基于 Python 的测试激励驱动与轻量级仿真 |

---

### 项目目录结构

```Plaintext
AGVS4RTL/
├── docker/                  # Docker 配置文件
│   ├── Dockerfile.parser    # Parser 镜像
│   ├── Dockerfile.gen       # Architect-Coding 镜像
│   └── Dockerfile.verify    # Verify 镜像 (集成 iverilog/Cocotb)
├── src/                     # 业务源代码
│   ├── common/              # Pydantic 协议模型与跨服务共享类型
│   ├── parser/              # Parser Agent 逻辑 (LangGraph Nodes)
│   ├── generator/           # 代码生成逻辑 (Architect & Coding)
│   └── verify/              # 验证逻辑 (Static Check & Dynamic Sim)
├── shared_workspace/        # 容器共享工作区 (挂载卷)
│   ├── specs/               # 结构化 Spec-Registry (JSON/YAML)
│   ├── rtl/                 # 生成的 Verilog 源码
│   └── sim/                 # 仿真产物 (VCD 波形, Log)
├── docker-compose.yml       # 三容器编排 (仅 parser 对外暴露)
├── requirements.txt         # Python 依赖定义
└── .env                     # 权限与密钥环境变量
```

---

### 未来改进项目

1. 扩展 **失败注入测试与重试闭环验收**。当前系统已完成 `FAIL_SEMANTIC -> prepare_retry -> PASS` 的最小 retry 修复闭环，下一阶段重点补充 `FAIL_COMPILE -> retry -> PASS`、`INFRA_ERROR` 不重试归档、达到 `max_iterations` 后失败归档等边界场景，使路由策略从“语义失败可修复”扩展到多 verdict 可验证。

2. 增强 Verify 的 **静态契约核查粒度**。当前 Verify Stub V1 已具备文件存在性检查、SpecReg 解析、最小顶层 module / ports 静态核查与可选的 `iverilog` 编译验证。下一阶段需要继续增强方向、位宽、时钟/复位映射、协议端口映射等更细粒度的契约检查能力，使 `FAIL_SEMANTIC` 的诊断结果更稳定、更适合驱动 Generator 修复。

3. 扩展 Verify 的 **动态仿真能力**。在 V1 Stub 稳定后，后续将逐步引入基于 `functional_requirements`、`corner_cases`、`illegal_conditions` 和 `verification_directives` 的测试激励生成能力，接入 `cocotb + iverilog` 形成从静态核查到动态行为验证的完整闭环。

4. 强化 Generator 的 **多轮修复利用能力**。Generator 已支持在 `iteration > 0` 时读取上一轮 `VerifyRpt` 与 `SpecReg`，并在 retry 轮产物摘要中体现上一轮 verdict。下一阶段需要让 Architect / Coder 节点更真实地消费 `VerifyRpt.error_details` 与 `suggested_fix`，形成面向 `FAIL_SEMANTIC`、`FAIL_COMPILE` 等失败类型的差异化修复策略。

5. 补充 **工作流异常治理与可观测性**。当前工作流已经具备基础 `trace` 记录与归档机制，后续可继续增加更细粒度的错误分类、节点级耗时统计、任务级日志关联、失败现场保留策略与验收脚本，提升联调效率与问题定位能力。

---

### 最新开发进度

1. 已完成 `src/common/models.py` 的第一轮稳定化重构，统一了 Parser / Generator / Verify 当前阶段使用的核心协议模型，并修复了 `strict=True` 导致 FastAPI 枚举字段跨服务传输失败的问题。

2. 已完成 Parser 工作流从最小生成闭环到完整编排闭环的恢复，当前主路径已扩展为 `parser_initialize -> gen_stateless -> verify_stateless -> route -> archive`，能够稳定完成任务初始化、UserTaskSpec 落盘、Generator 调度、Verify 调度、结果路由与归档。

3. 已完成 Generator 内部 LangGraph 骨架重构，形成 `init_context -> architect -> coder -> finalize` 四节点流程，并在不依赖 LLM 接口的情况下实现基于规则占位的 `SpecReg` 与 Verilog RTL 生成。

4. 已完成 Verify Stub V1 的最小实现，形成 `init_context -> semantic_check -> compile_check -> finalize` 四节点流程，支持 `SpecReg` / RTL 文件存在性检查、SpecReg 解析校验、顶层 module / ports 的最小静态契约核查，以及可选的 `iverilog` 编译校验。

5. 已固化 Verify 侧报告落盘约定：当前验证报告统一输出到 `shared_workspace/TASK_ID/sim/VerifyRpt_iter{iteration}.json`，编译日志输出到 `shared_workspace/TASK_ID/sim/compile_iter{iteration}.log`，与 Generator 侧的 `SpecReg_iter{iteration}.json` 形成版本对应关系。

6. 已完成 Docker 三服务联调与运行时挂载修正：当前 Parser 对外映射端口为 `8001`，Generator / Verify 保持仅容器内可见；同时已补齐 `Output` 与 `shared_workspace` 的统一挂载，解决此前归档结果仅存在容器内部、宿主机不可见的问题。

7. 已成功跑通首个 `Parser + Generator + Verify Stub` 端到端样例，系统可返回 `WorkflowRunResult(success=true)`，并在宿主机 `Output/TASK_ID/Result/shared_workspace/` 下产出 `UserTaskSpec.json`、`SpecReg_iter0.json`、`{top_module}.v`、`VerifyRpt_iter0.json` 与编译日志等完整中间产物。

8. 已完成 retry 修复闭环的最小验收：通过宿主机脚本覆盖普通 PASS 主路径，以及 `FAIL_SEMANTIC -> prepare_retry -> PASS` 场景。当前 Parser 可稳定执行 `parser_initialize -> gen_stateless -> verify_stateless -> prepare_retry -> gen_stateless -> verify_stateless -> archive_success`，Generator 在 retry 轮会读取上一轮 `VerifyRpt_iterN.json`，最终归档保留第 0/1 轮 SpecReg 与 VerifyRpt。