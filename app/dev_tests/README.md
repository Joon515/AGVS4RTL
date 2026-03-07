# 开发测试脚本目录

本目录集中存放“脚本式开发测试”，用于本地/容器快速验证。

## 脚本清单

- `_bootstrap.py`：开发脚本公共启动引导（统一 `PROJECT_ROOT` 与导入路径）
- `run_pre_manager_workflow.py`：Pre-Manager 端到端流程脚本
- `run_pre_manager_unit_basic.py`：Pre-Manager 无 LLM 依赖脚本测试
- `run_tui.py`：TUI 基础功能脚本测试
- `run_tui_components.py`：TUI 组件级脚本测试
- `run_config_workflow.py`：配置保存/加载/加密流程验证
- `run_encryption.py`：加解密单项验证
- `run_test_agent_docker_integration.py`：TestAgent + Sandbox 集成验证

## 常用命令

```bash
python3 app/dev_tests/run_tui.py
python3 app/dev_tests/run_config_workflow.py
python3 app/dev_tests/run_encryption.py
python3 app/dev_tests/run_pre_manager_workflow.py
python3 app/dev_tests/run_pre_manager_unit_basic.py
```

Docker 环境：

```bash
docker compose exec agent-core python3 app/dev_tests/run_pre_manager_unit_basic.py
timeout 300s docker compose exec -T agent-core python3 app/dev_tests/run_test_agent_docker_integration.py
```
