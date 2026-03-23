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
