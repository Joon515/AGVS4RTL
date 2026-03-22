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
