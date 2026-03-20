# 2026-03-21

- 同步 `pyproject.toml` 依赖到 FastAPI 架构：移除 `celery`、`redis`，新增 `fastapi`、`uvicorn`、`httpx`，并将 `semantic-router` 作为核心依赖。
- 删除过渡遗留文件 `src/parser/worker.py`（Celery 任务定义），避免与当前服务化入口模式混淆。
- 说明：`parser` optional extra 暂保留为空扩展位，后续如需按服务拆分依赖可再补充。
