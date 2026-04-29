# 2026-03-21

- 同步 `pyproject.toml` 依赖到 FastAPI 架构：移除 `celery`、`redis`，新增 `fastapi`、`uvicorn`、`httpx`，并将 `semantic-router` 作为核心依赖。
- 删除过渡遗留文件 `src/parser/worker.py`（Celery 任务定义），避免与当前服务化入口模式混淆。
- 说明：`parser` optional extra 暂保留为空扩展位，后续如需按服务拆分依赖可再补充。
- 精简 docker-compose 回三服务运行形态，移除临时 `base` 服务。
- 调整容器网络暴露策略，仅 `parser` 通过宿主机端口对外提供 IO，`gen` 与 `verify` 改为容器内 `expose`。
- 为避免依赖临时 `base` 服务镜像构建，`parser`、`gen`、`verify` Dockerfile 现各自包含最小可构建基础环境。
- 删除 `docker/Dockerfile.base`，避免仓库中保留已不再参与构建链的过时文件。
- 补齐 `src/parser/main.py`、`src/generator/main.py`、`src/verify/main.py` 三个最小 FastAPI 入口；健康检查模型保留在各入口内部，不并入 `src/common/models.py` 的跨服务契约层。
- 依赖管理从 `uv + pyproject.toml` 切换为 `pip + requirements.txt`，同步改造三个 Dockerfile 的安装流程。
  - 删除 `pyproject.toml`；根目录新增 `requirements.txt` 统一声明三服务共用依赖（fastapi/uvicorn/httpx/pydantic/langgraph/semantic-router/pyverilog/cocotb/cocotb-test/pytest）。
  - Dockerfile 由 `COPY --from=ghcr.io/astral-sh/uv` 拉取 uv 改为直接 `pip install --no-cache-dir -r requirements.txt`，移除 `UV_PROJECT_ENVIRONMENT` 环境变量。

# 2026-03-22

- Docker build + 全服务健康检查验证通过：`parser`（8001）对外健康，`gen:8000`、`verify:8000` 容器内网健康；`/health` 端点返回正常，`httpx` 跨容器调用无异常。

# 2026-03-23

- 依赖策略调整：`requirements.txt` 取消所有 `>=` 最低版本约束，改为仅保留包名，安装时默认拉取可解析到的最新版本。
- 说明：该调整不涉及 Dockerfile / Compose 底层结构修改，仅变更 Python 依赖声明策略。
- 兼容性复验：执行 `docker compose build` + `docker compose up -d --force-recreate` 完整重建，三服务均正常启动。
- 联通性验证：外部 `http://localhost:8001/health` 返回 200；Parser 容器内访问 `gen:8000/health`、`verify:8000/health` 均返回 200，确认升级后依赖组合与当前服务骨架兼容。
- 依赖策略回调：重新加回 `>=` 最低版本约束，并将下限提升至本轮验证可用的较新版本（覆盖 FastAPI/Pydantic/LangGraph 等），兼顾新特性可用性与安装稳定性。
- 新增 Parser LangGraph 工作流骨架：`src/parser/workflow.py` 形成三容器主链 `parser_prepare -> gen_stateless -> verify_stateless -> finalize`，并在 verify 后按 `VerifyVerdict` 进行条件分支。
- 新增 Parser 编排入口：`src/parser/main.py` 增加 `POST /v1/workflow/run`，统一触发状态机并返回执行轨迹 `trace`。
- 将 Gen / Verify 节点定义为无状态服务：
  - `src/generator/main.py` 增加 `POST /v1/generate`。
  - `src/verify/main.py` 增加 `POST /v1/verify`。
- 在 `src/common/models.py` 增补工作流协议模型：`WorkflowRunRequest`、`WorkTaskPayload`、`GenNodeOutput`、`VerifyTaskPayload`、`VerifyNodeOutput`、`WorkflowRunResult`。
- Docker 内联通冒烟验证通过：调用 `POST /v1/workflow/run` 可返回 `finalize_success`，并包含 Gen/Verify 节点执行轨迹。
- 备注：容器内 `compileall` 受共享卷 `__pycache__` 写权限影响，已改为“只编译不落盘”语法校验方式完成检查。

# 2026-03-24

- 按 Parser 技术定义重构状态机行为：新增任务冷启动节点，接收请求后立即创建 `/Output/TASK_ID/{Origin,Archive,Result}` 与 `/shared_workspace/TASK_ID/{specs,rtl,sim}` 目录并落盘原始输入。
- Parser 语义路由新增占位策略：当 `WorkflowRunRequest.intent` 为空时，基于 `raw_input_text` 关键词判定 `IntentCategory`（fix/verify/modify/default）。
- 轻量通信改造完成：模块间传输从大对象切换为路径协议，`WorkTaskPayload` 传递 `spec_file_path` + `iteration` + `shared_task_dir`，Gen/Verify 通过文件路径读取上下文。
- Gen 无状态节点升级：生成 `SpecReg_iterN.json` 与 RTL 文件并写入共享任务目录，仅回传 `spec_file_path` 与 `rtl_path`。
- Verify 无状态节点升级：读取 `spec_file_path` 与 `rtl_path` 做存在性校验，产出 `VerifyRpt`（含 `verdict` 与 `error_details`）并写入 `sim` 目录。
- Parser 编排器支持迭代判定：依据 `VerifyNodeOutput.report.verdict` 决策 PASS 归档、FAIL 重试或失败归档；达到最大轮次后终止。
- 归档与清理落地：任务结束后将共享工作区产物复制到 `Output/TASK_ID/Result` 或 `Archive`，随后清理 `shared_workspace/TASK_ID`。
- Docker 联通复验通过：`/v1/workflow/run` 返回 `final_stage=archive_success`，轨迹覆盖 `parser_initialize -> gen_stateless -> verify_stateless -> archive_success`。

# 2026-04-12

- 重构 `SpecReg` 核心数据模型：将其从扁平的实例列表升级为契合硬件特征的有向图结构（Graph Structure），引入 `RtlNode`、`RtlEdge` 和强类型枚举 `NodeType`（包含 `INSTANCE`, `COMBINATIONAL`, `SEQUENTIAL`），以便在多轮对话中渐进式细化模块层级。
- 为 Gen Agent 引入基于 LangGraph 的内部工作流（`src/generator/workflow.py`），拆分出 `init_context_node`（读取前置规约与验证报错）、`architect_node`（类图节点细化）、`coder_node`（RTL代码生成）以及 `finalize_node`（归档落盘）四个核心节点。
- 改造 `src/generator/main.py` 的 `/v1/generate` 接口，使其将任务委派给无状态的 LangGraph 工作流实例，确保服务级别的无状态性与图级别的局部状态流转。
- 完善 `Agent_DEF.md` 中关于 Gen Agent 的技术规范，明确其内部 I/O 网络隔离、共享工作区访问机制以及扮演“架构师+程序员”的双重身份实现多轮对话修复。

# 2026-04-17 v1

- 重构 `src/common/models.py` 协议层：补全 `BaseSyncMeta`、`UserTaskSpec`、`SpecReg`、`VerifyRpt`、`WorkflowRunRequest`、`WorkTaskPayload`、`GenNodeOutput`、`VerifyTaskPayload`、`WorkflowRunResult` 等核心 Pydantic 数据模型；引入 `TaskPaths` 与 `build_task_paths()` 统一任务目录布局，增强多服务间的文件路径契约一致性。
- 为 `models.py` 新增多组统一校验辅助函数，包括 `_validate_non_empty_str`、`_validate_non_empty_str_list`、`_validate_optional_non_empty_str`、`_validate_optional_identifier`、`_index_ports_by_name`、`_index_nodes_by_id`，收敛重复校验逻辑，提升模型可维护性。
- 增强 `SpecReg` 结构表达能力：在已有参数、端口、时钟复位、协议编组基础上，补充 `functional_requirements`、`corner_cases`、`illegal_conditions`、`latency_notes`，并通过 `RtlNode` / `RtlEdge` / `EndpointRef` 明确 RTL 图结构语义。
- 为 `SpecReg` 和 `VerifyRpt` 增加面向编排器的辅助方法：如 `port_map()`、`node_map()`、`top_input_ports()`、`is_flat_design()`、`is_pass()`、`is_retryable()`、`requires_arch_refactor()`、`suggested_refactor_level()` 等，使模型不仅是静态协议，也可承载部分轻量业务语义。
- 修正 `StrictBaseModel` 的全局严格模式配置：移除 `strict=True`，保留 `extra="forbid"` 与 `validate_assignment=True`。解决 FastAPI 在跨服务 JSON 通信中无法将字符串枚举值（如 `"GEN_WITH_TEST"`）解析为 `IntentCategory` 的问题，打通 Parser → Generator 的实际接口请求链路。
- 重构 `src/parser/workflow.py`：将工作流从原先预留 Verify 的全闭环编排，临时收缩为当前阶段的最小闭环状态机 `parser_initialize -> gen_stateless -> archive_success`，以优先验证 Parser 与 Generator 的文件协议和生成链路。
- 在 Parser 工作流中接入 `TaskPaths` 统一目录管理逻辑，实现任务初始化时自动创建：
  - `Output/TASK_ID/Origin`
  - `Output/TASK_ID/Archive`
  - `Output/TASK_ID/Result`
  - `shared_workspace/TASK_ID/specs`
  - `shared_workspace/TASK_ID/rtl`
  - `shared_workspace/TASK_ID/sim`
- 完成 Parser 冷启动节点的规范化落盘：请求进入后自动生成 `task_id`、落盘原始输入、构建并保存 `UserTaskSpec.json` 到 Output 根目录与 SharedWorkspace/specs，确保后续 Generator 仅读路径即可获取任务上下文。
- 修复 `WorkflowRunRequest` 与 `UserTaskSpec` 在 `refined_requirements` 约束上的衔接问题：当请求仅提供 `raw_input_text` 而未显式传入 `refined_requirements` 时，由 Parser 自动构造兜底需求列表，避免初始化阶段因 `min_length=1` 约束失败。
- 重构 `src/parser/main.py`：补充日志、统一接口注释、明确同步阻塞式工作流执行语义，并保留 `ApiResponse[WorkflowRunResult]` 作为对外统一响应结构。
- 重构 `src/generator/workflow.py`：将 Generator 内部工作流组织为 `init_context -> architect -> coder -> finalize` 四节点 LangGraph 状态机，其中：
  - `init_context` 负责读取 `UserTaskSpec`，并在重试轮次尝试加载上一轮 `SpecReg` 与 `VerifyRpt`
  - `architect` 负责生成结构化 `SpecReg`
  - `coder` 负责基于 `SpecReg` 输出 RTL 代码
  - `finalize` 负责统一落盘 `SpecReg_iterN.json` 与 Verilog 文件，并返回 `GenNodeOutput`
- 修复 Generator 与当前 `models.py` 的协议不一致问题：将 `RtlEdge.source/target` 从旧字符串形式改为 `EndpointRef` 结构化端点，确保 `SpecReg` 能通过当前 Pydantic 模型校验。
- 完善 Generator 的占位实现，使其在**不接入 LLM 的情况下也可独立运行**：当前通过规则化 `SpecReg` 构造函数与简单模板式 RTL 输出函数，先行打通“结构化规约生成 + Verilog 落盘”最小链路。
- 小修 `src/generator/main.py`：清理无用 import、补充日志与中文注释，保留 `/v1/generate` 的轻量协议接口，确保内部服务职责单一。
- 完成 Docker 三服务最小联调验证：确认 Parser 对外宿主机暴露端口为 `8001`，Generator / Verify 保持仅容器内网络可见，符合三容器隔离拓扑设计。
- 打通 **Parser + Generator 最小闭环**：成功通过 `/v1/workflow/run` 发起任务，请求经 Parser 初始化后转交 Generator，生成 `SpecReg_iter0.json` 与 `{top_module}.v`，再由 Parser 自动归档到 `Output/TASK_ID/Result/shared_workspace`。
- 首次获得端到端成功响应，返回结果包含：
  - `task_id`
  - `final_stage=archive_success`
  - `success=true`
  - `trace=[parser_initialize, gen_stateless, archive_success]`
  - `gen_output.spec_file_path`
  - `gen_output.rtl_path`

---

# 2026-04-17 v2

- 完成 `src/verify/workflow.py` 的 V1 骨架实现，整体风格对齐 `src/generator/workflow.py`，采用 LangGraph 内部状态机组织最小验证流程，当前节点路径为 `init_context -> semantic_check -> compile_check -> finalize`。
- 完成 `src/verify/main.py` 的内部服务化封装，新增 `/v1/verify` 与 `/health` 接口，统一使用 `ApiResponse[VerifyNodeOutput]` 作为返回协议，保持与 Parser / Generator 服务层实现风格一致。
- 落地 Verify Stub V1 的最小验证能力：支持 `SpecReg` 文件存在性检查、RTL 文件存在性检查、`SpecReg` 反序列化校验、顶层 module / ports 的最小静态契约检查，以及可选的 `iverilog` 编译检查。
- 固化 Verify 侧输出约定：验证报告落盘到 `shared_workspace/TASK_ID/sim/VerifyRpt_iter{iteration}.json`，编译日志落盘到 `shared_workspace/TASK_ID/sim/compile_iter{iteration}.log`，与 Generator 侧 `SpecReg_iter{iteration}.json` 形成版本对应关系。
- 恢复 Parser 完整工作流编排，当前对外主路径已由最小生成闭环重新扩展为 `parser_initialize -> gen_stateless -> verify_stateless -> route -> archive`，并重新接通验证后路由与成功/失败归档逻辑。
- 完成 Parser / Generator / Verify 三服务联调，确认 `parser` 可通过容器内网络访问 `http://gen:8000` 与 `http://verify:8000`，内部健康检查与服务调度链路均已打通。
- 修正 `docker-compose.yml` 中的运行时挂载配置，统一为三服务补齐 `./Output:/app/Output` 与 `./shared_workspace:/app/shared_workspace`，解决此前归档结果仅存在容器内文件系统、宿主机不可见的问题。
- 修正 Compose 侧 `Output` 挂载路径大小写不一致问题，统一使用 `/app/Output`，与 `WorkflowRunRequest.output_root` 默认值及 Parser 归档逻辑保持一致，避免 Linux 容器内因路径大小写敏感导致的结果目录漂移。
- 完成最小闭环验收：通过 Parser 外部入口 `POST /v1/workflow/run` 成功跑通 `UserTaskSpec -> SpecReg -> RTL -> VerifyRpt -> Archive` 全链路，返回 `WorkflowRunResult(success=true)`，并在宿主机 `Output/TASK_ID/Result/shared_workspace/` 下确认产物完整落盘。
- 当前系统阶段性状态更新为：`Parser + Generator + Verify Stub V1` 最小生成-验证-归档闭环已可运行，下一阶段将优先补充失败注入测试与 retry 路径验收，再逐步增强 Verify 的静态契约检查粒度与多轮修复闭环能力。

---

# 2026-04-17 v3

- 完成 Verify Stub V1 接入与联调，恢复 Parser -> Gen -> Verify -> Archive 最小闭环。
- 完成 Verify 服务 API 与内部 LangGraph 工作流骨架落地，形成 init_context -> semantic_check -> compile_check -> finalize 四节点流程。
- 完成 VerifyRpt_iterN.json 与 compile_iterN.log 的共享工作区落盘约定，目录统一为 shared_workspace/TASK_ID/sim/。
- 完成 Verify Stub V1 失败注入测试，已验证以下 verdict 分支可用：
  - PASS
  - INFRA_ERROR（SpecReg 缺失 / RTL 缺失）
  - FAIL_COMPILE（RTL 语法错误）
  - FAIL_SEMANTIC（顶层端口与 SpecReg 不匹配）
- 当前系统已具备最小“生成 + 验证 + 归档”闭环能力，为后续 retry 修复闭环与 Verify 动态仿真扩展提供稳定基线。

# 2026-04-29

- 完成 retry 修复闭环的最小验收实现：Parser 已可稳定执行 `parser_initialize -> gen_stateless -> verify_stateless -> prepare_retry -> gen_stateless -> verify_stateless -> archive_success`。
- 将 `prepare_retry` 轨迹状态从 `error` 调整为 `success`，明确其语义为“已成功准备下一轮生成”，避免测试与后续可观测性把可恢复失败误判为节点执行失败。
- 为 Generator 增加轻量失败注入钩子，用于验收闭环而不改跨服务协议：`AGVS4RTL_INJECT_FAIL_SEMANTIC_ONCE` 会在第 0 轮生成缺失 `o_done` 端口的 RTL，第 1 轮恢复到保守正确模板；同时预留 `AGVS4RTL_INJECT_FAIL_COMPILE_ONCE` 用于后续编译失败闭环测试。
- Generator 在重试轮次成功读取上一轮 `VerifyRpt_iterN.json` 后，会在 `GenNodeOutput.summary` 中记录上一轮 verdict，便于宿主机测试确认 `prepare_retry -> gen_stateless` 确实消费了上一轮验证报告。
- 扩展 `test_host_workflow.py`，覆盖两个宿主机端到端场景：普通 PASS 主路径，以及 `FAIL_SEMANTIC -> retry -> PASS` 修复闭环。
- 验证结果：使用 `.venv-1/bin/python test_host_workflow.py` 跑通，retry 样例归档到 `Output/TASK_20260429T020447Z_af797796/Result/shared_workspace/`，其中 `VerifyRpt_iter0.json` verdict 为 `FAIL_SEMANTIC`，`VerifyRpt_iter1.json` verdict 为 `PASS`，并保留 `SpecReg_iter0.json`、`SpecReg_iter1.json` 与最终 RTL。
- 语法检查：宿主机系统 Python 因仓库内既有 `src/**/__pycache__` 权限问题无法直接写入 pyc，已改用 `PYTHONPYCACHEPREFIX=/tmp/agvs4rtl_pycache /usr/bin/python3 -m py_compile ...` 完成关键文件语法编译检查。

# 2026-04-29 v2

- 扩展宿主机端到端验收脚本，新增 `FAIL_COMPILE -> prepare_retry -> PASS` 闭环场景，覆盖 Generator 第 0 轮注入 Verilog 语法错误、Verify 产出 `FAIL_COMPILE`、Parser 路由到 `prepare_retry`、第 1 轮 Generator 恢复正确 RTL 并最终 PASS 的完整路径。
- 当前 `test_host_workflow.py` 已覆盖三条路径：普通 PASS 主路径、`FAIL_SEMANTIC -> retry -> PASS`、`FAIL_COMPILE -> retry -> PASS`。
- 验证结果：使用 `.venv-1/bin/python test_host_workflow.py` 跑通，编译失败 retry 样例归档到 `Output/TASK_20260429T022026Z_58f4b115/Result/shared_workspace/`，其中 `VerifyRpt_iter0.json` verdict 为 `FAIL_COMPILE`，`VerifyRpt_iter1.json` verdict 为 `PASS`。
- 语法检查：继续使用 `PYTHONPYCACHEPREFIX=/tmp/agvs4rtl_pycache /usr/bin/python3 -m py_compile src/common/models.py src/parser/workflow.py src/generator/workflow.py src/verify/workflow.py test_host_workflow.py`，关键 Python 文件均可编译。

# 2026-04-29 v3

- 新增 `INFRA_ERROR -> archive_failed` 非重试路径验收，证明 `VerifyRpt.is_retryable()` 不会把基础设施错误纳入 `prepare_retry` 修复循环。
- Generator 增加 `AGVS4RTL_INJECT_INFRA_MISSING_RTL_ONCE` 验收钩子：第 0 轮写出 SpecReg 后删除 RTL 文件，使 Verify 在读取 RTL 阶段稳定产出 `INFRA_ERROR`，用于验证 Parser 路由策略。
- `test_host_workflow.py` 当前覆盖四条宿主机端到端路径：普通 PASS 主路径、`FAIL_SEMANTIC -> retry -> PASS`、`FAIL_COMPILE -> retry -> PASS`、`INFRA_ERROR -> archive_failed`。
- 验证结果：重启 Generator 服务后使用 `.venv-1/bin/python test_host_workflow.py` 跑通，INFRA 样例归档到 `Output/TASK_20260429T022447Z_7179f99e/Archive/shared_workspace/`，其中 `VerifyRpt_iter0.json` verdict 为 `INFRA_ERROR`，执行轨迹为 `parser_initialize -> gen_stateless -> verify_stateless -> archive_failed`。