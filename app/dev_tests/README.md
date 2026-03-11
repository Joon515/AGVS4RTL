# 开发测试脚本目录

本目录集中存放“脚本式开发测试”，用于本地/容器快速验证。

## 脚本清单

- `_bootstrap.py`：开发脚本公共启动引导（统一 `PROJECT_ROOT` 与导入路径）
- `run_pre_manager_workflow.py`：Pre-Manager 端到端流程脚本
- `run_pre_manager_unit_basic.py`：Pre-Manager 无 LLM 依赖脚本测试
- `run_cloud_multiagent_smoke.py`：云端连通 + 多 Agent 预处理流程冒烟
- `run_dual_model_codegen_smoke.py`：全链路代码生成冒烟（Parser/Architect/Codegen/Verify）
- `run_four_agent_consistency_smoke.py`：四 Agent 严格一致性冒烟
- `run_four_agent_consistency_smoke_mvp.py`：四 Agent MVP 一致性冒烟（推荐日常回归）
- `run_generate_agent_round_records.py`：按 Agent 目录落盘一轮输出记录
- `run_model_behavior_probe.py`：模型行为探针（延迟/输出质量对比）
- `run_tui.py`：TUI 基础功能脚本测试
- `run_tui_components.py`：TUI 组件级脚本测试
- `run_config_workflow.py`：配置保存/加载/加密流程验证
- `run_encryption.py`：加解密单项验证
- `run_test_agent_docker_integration.py`：TestAgent + Sandbox 集成验证
- `test_generate_prompt_templates.py`：GenerateAgent 的 Jinja2 提示词模板集成单测（pytest）

## 常用命令

```bash
python3 app/dev_tests/run_tui.py
python3 app/dev_tests/run_config_workflow.py
python3 app/dev_tests/run_encryption.py
python3 app/dev_tests/run_pre_manager_workflow.py
python3 app/dev_tests/run_pre_manager_unit_basic.py
python3 app/dev_tests/run_four_agent_consistency_smoke_mvp.py --result-json data/workspace/test_output/dual_model_codegen_smoke.json
python3 app/dev_tests/run_generate_agent_round_records.py --result-json data/workspace/test_output/dual_model_codegen_smoke.json
python3 -m pytest app/dev_tests/test_generate_prompt_templates.py -q
```

Docker 环境：

```bash
docker compose exec agent-core python3 app/dev_tests/run_pre_manager_unit_basic.py
timeout 300s docker compose exec -T agent-core python3 app/dev_tests/run_test_agent_docker_integration.py
```
