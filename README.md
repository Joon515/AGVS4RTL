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

1. 扩展 **失败注入测试与重试闭环验收**。当前系统已完成 `FAIL_SEMANTIC -> prepare_retry -> PASS`、`FAIL_COMPILE -> prepare_retry -> PASS` 与 `INFRA_ERROR -> archive_failed` 的路由验收，下一阶段重点补充达到 `max_iterations` 后失败归档等边界场景，使路由策略从“可修复失败能重试”扩展到“不可修复/超限失败可归档”。

2. 增强 Verify 的 **静态契约核查粒度**。当前 Verify Stub V1 已具备文件存在性检查、SpecReg 解析、顶层 module / ports 存在性、端口方向、端口位宽核查与可选的 `iverilog` 编译验证。下一阶段需要继续增强时钟/复位映射、协议端口映射等更细粒度的契约检查能力，使 `FAIL_SEMANTIC` 的诊断结果更稳定、更适合驱动 Generator 修复。

3. 扩展 Verify 的 **动态仿真能力**。在 V1 Stub 稳定后，后续将逐步引入基于 `functional_requirements`、`corner_cases`、`illegal_conditions` 和 `verification_directives` 的测试激励生成能力，接入 `cocotb + iverilog` 形成从静态核查到动态行为验证的完整闭环。

4. 强化 Generator 的 **多轮修复利用能力**。Generator 已支持在 `iteration > 0` 时读取上一轮 `VerifyRpt` 与 `SpecReg`，并在 retry 轮产物摘要中体现上一轮 verdict。下一阶段需要让 Architect / Coder 节点更真实地消费 `VerifyRpt.error_details` 与 `suggested_fix`，形成面向 `FAIL_SEMANTIC`、`FAIL_COMPILE` 等失败类型的差异化修复策略。

5. 补充 **工作流异常治理与可观测性**。当前工作流已经具备基础 `trace` 记录与归档机制，后续可继续增加更细粒度的错误分类、节点级耗时统计、任务级日志关联、失败现场保留策略与验收脚本，提升联调效率与问题定位能力。

---

### 最新开发进度

1. 已完成 `src/common/models.py` 的第一轮稳定化重构，统一了 Parser / Generator / Verify 当前阶段使用的核心协议模型，并修复了 `strict=True` 导致 FastAPI 枚举字段跨服务传输失败的问题。

2. 已完成 Parser 工作流从最小生成闭环到完整编排闭环的恢复，当前主路径已扩展为 `parser_initialize -> gen_stateless -> verify_stateless -> route -> archive`，能够稳定完成任务初始化、UserTaskSpec 落盘、Generator 调度、Verify 调度、结果路由与归档。

3. 已完成 Generator 内部 LangGraph 骨架重构，形成 `init_context -> architect -> coder -> finalize` 四节点流程。Architect 负责维护 `SpecReg` 设计契约，Coder 负责依据 `SpecReg` 生成 Verilog RTL；未启用 LLM 或包含验收注入钩子时保持规则化路径，启用 LLM 时 Architect 可生成经过 Pydantic 校验的真实 `SpecReg`。

4. 已完成 Verify Stub V1 的阶段性实现，形成 `init_context -> semantic_check -> compile_check -> finalize` 四节点流程，支持 `SpecReg` / RTL 文件存在性检查、SpecReg 解析校验、顶层 module / ports 严格一致性、端口方向、端口位宽核查，以及可选的 `iverilog` 编译校验。

5. 已固化 Verify 侧报告落盘约定：当前验证报告统一输出到 `shared_workspace/TASK_ID/sim/VerifyRpt_iter{iteration}.json`，编译日志输出到 `shared_workspace/TASK_ID/sim/compile_iter{iteration}.log`，与 Generator 侧的 `SpecReg_iter{iteration}.json` 形成版本对应关系。

6. 已完成 Docker 三服务联调与运行时挂载修正：当前 Parser 对外映射端口为 `8001`，Generator / Verify 保持仅容器内可见；同时已补齐 `Output` 与 `shared_workspace` 的统一挂载，解决此前归档结果仅存在容器内部、宿主机不可见的问题。

7. 已成功跑通首个 `Parser + Generator + Verify Stub` 端到端样例，系统可返回 `WorkflowRunResult(success=true)`，并在宿主机 `Output/TASK_ID/Result/shared_workspace/` 下产出 `UserTaskSpec.json`、`SpecReg_iter0.json`、`{top_module}.v`、`VerifyRpt_iter0.json` 与编译日志等完整中间产物。

8. 已完成 retry 修复闭环、非重试失败归档与静态契约细节的最小验收：通过宿主机脚本覆盖普通 PASS 主路径、`FAIL_SEMANTIC -> prepare_retry -> PASS`、`FAIL_COMPILE -> prepare_retry -> PASS`、`INFRA_ERROR -> archive_failed`、端口方向 mismatch retry 与端口位宽 mismatch retry 场景。当前 Parser 可稳定执行可重试失败的二轮修复路径，并对不可重试基础设施错误直接进入失败归档。

9. 已补入 LLM 运行时配置与三服务接入路径：Parser 可通过请求体 `llm` 字段或环境变量读取 `enabled`、`base_url`、`api_key`、`model`、`profile`，并通过内部请求头转发给 Generator / Verify。Parser 在启用 LLM 时优先做 intent 分类、需求提炼、协议约束与设计红线识别；Generator 的 Architect 节点可调用同一 OpenAI-compatible Chat Completions 配置生成 `SpecReg`，Coder 节点再基于该契约生成 RTL，并在 retry 轮次携带上一轮 `SpecReg` / `VerifyRpt` 上下文；Verify 仅把 LLM 用于失败诊断增强，不改变确定性 verdict。API key 仅作为运行时信息传递，不写入 `UserTaskSpec`、trace、`Output/` 或 `shared_workspace/`。

### 阶段产物契约

当前系统按以下产物边界收敛：Parser 负责 Agent 路由与 `UserTaskSpec` 维护；Generator / Architect 负责生成并维护权威 `SpecReg`；Generator / Coder 只依据 `SpecReg` 生成 RTL；Verify 负责读取 `SpecReg` 与 RTL，生成 `VerifyRpt`，并通过静态契约检查、编译检查、后续仿真与诊断建议驱动 Parser 回溯重试。Parser 只根据 `VerifyRpt` 做 PASS、retry 或 archive 路由，不直接解释 RTL 细节。

### LLM 接口配置

本地开发可复制 `.env.example` 为 `.env` 后填写真实配置。`.env` 已被 `.gitignore` 排除，不应提交真实 API key。

```bash
AGVS4RTL_LLM_ENABLED=true
AGVS4RTL_LLM_BASE_URL=https://example.com/v1
AGVS4RTL_LLM_API_KEY=your-api-key
AGVS4RTL_LLM_MODEL=your-model
AGVS4RTL_LLM_PROFILE=default
```

也可以在调用 Parser 时传入非持久化运行时配置：

```json
{
	"top_module": "seq_done_logic",
	"raw_input_text": "Generate a simple sequential done logic module",
	"max_iterations": 2,
	"llm": {
		"enabled": true,
		"base_url": "https://example.com/v1",
		"api_key": "your-api-key",
		"model": "your-model",
		"profile": "default"
	}
}
```

#### Parser → Generator 超时配置

Parser 调用 Generator 默认超时 240 秒（环境变量 `GEN_SERVICE_TIMEOUT_SECONDS`），适配真实 LLM 生成慢路径。可通过 compose/env 配置。

当前阶段已接入 OpenAI-compatible Chat Completions 接口，`base_url` 可以填写服务根路径（如 `https://example.com/v1`）或完整 `/chat/completions` 路径。请求体 `llm` 配置优先级高于环境变量；当 `enabled=false` 或配置缺失时，系统保持规则化路径运行。

#### 模糊需求 smoke 测试

`test_fuzzy_requirement_workflow.py` 用于验证“只给模糊自然语言、不提供精确端口和 opcode 列表”的真实 LLM 路径。该脚本不会传入 `refined_requirements`，预期 Parser LLM 先补全 `UserTaskSpec`，Architect LLM 再生成真实 `SpecReg`，并确认最终 `SpecReg` 至少包含 8 位输入、8 位输出，且没有回退到默认 `i_clk/i_rst_n/o_done` dummy 契约。

```bash
.venv-1/bin/python test_fuzzy_requirement_workflow.py
```

该 smoke 依赖 compose 环境中的 `AGVS4RTL_LLM_ENABLED=true` 以及可用模型配置；确定性规则路径回归仍使用 `.venv-1/bin/python test_host_workflow.py`。

#### Parser / Generator 接入行为

Parser 是 LLM 配置入口与跨服务转发点。启用 LLM 后，Parser 会先调用 Parser LLM 生成结构化 `ParserLlmAnalysis`，用于 intent 分类、需求提炼、目标协议和设计规则识别；如果请求体已经显式给出 `intent` 或 `refined_requirements`，这些显式字段仍优先保留。Parser LLM 调用失败、返回空内容或返回内容无法通过模型校验时，会自动回退到关键词路由和原始需求兜底，不中断主流程。Parser LLM 对话记录落盘到 `shared_workspace/TASK_ID/llm/ParserChat_iter0.json`，仅包含 messages、非敏感请求参数、响应内容和错误摘要。

Parser 调用 Generator / Verify 时，会通过 `X-AGVS4RTL-LLM-*` 内部请求头转发运行时配置。Generator API 解析这些请求头后传入内部 LangGraph workflow；Architect 节点在 LLM 启用且任务中不含 `AGVS4RTL_INJECT_*` 验收钩子时调用模型生成 `SpecReg` JSON，并用 `SpecReg.model_validate(...)` 做强校验。若 Architect LLM 失败，系统会记录失败 transcript 并回退到规则化 `SpecReg`，保持服务可用。Coder 节点随后只依据本轮 `SpecReg` 生成 RTL；在 LLM 启用且无注入钩子时调用模型生成 Verilog。retry 轮次会把上一轮 `SpecReg` 与 `VerifyRpt` 加入提示词，使 Architect / Coder 能看到失败 verdict、错误详情和上一轮结构化规约。Generator LLM 对话记录按阶段落盘到 `shared_workspace/TASK_ID/llm/ArchitectChat_iterN.json` 与 `shared_workspace/TASK_ID/llm/CoderChat_iterN.json`。

#### Verify 诊断边界

Verify 在规则化静态契约检查或编译检查产出失败 verdict 后，才会调用同一运行时 LLM 配置补充诊断建议。PASS / FAIL / INFRA_ERROR 的裁判仍由 Verify 的确定性节点负责；LLM 调用失败只记录诊断不可用的 transcript，不会改变 `VerifyRpt.verdict`、`error_details` 或 retry 语义。静态契约检查要求 RTL 顶层端口集合与 `SpecReg.ports` 严格一致，缺失端口、方向不匹配、位宽不匹配和额外端口都会进入 `FAIL_SEMANTIC`。Verify 对话记录落盘到 `shared_workspace/TASK_ID/llm/VerifyChat_iterN.json`。
