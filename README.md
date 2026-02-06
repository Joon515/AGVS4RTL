# AGVS4RTL

AGVS4RTL 是一个基于 LLM 的 HDL 生成与验证系统。本次开发补齐了预处理数据结构与 Rich TUI 仪表盘，并增加了基于 PQC 的 API Key 加密配置能力。

## 新增功能概览

- 预处理数据结构：标准化自然语言需求与约束输出
- Rich TUI 仪表盘：日志入口、输入框、任务列表、参数配置、模块架构图
- Agent 配置中心：每个 agent 的模型参数与 loop 预算
- API Key 强制 TUI 输入并使用 Kyber(PQC) + AES-GCM 加密存储

## 主要文件

- 预处理与数据结构：app/pre_agent/stracture_request.py
- TUI 仪表盘：app/ui/tui.py
- 配置加密：app/ui/config_store.py
- TUI 测试与演示：app/ui/test_tui.py、app/ui/demo_tui.py
- 配置规范文档：docs/spec/agent-config.md

## TUI 使用说明

启动后显示仪表盘：

- 任务列表：显示状态与耗时/循环数
- 日志入口：显示 data/log 下最近 5 条日志
- 预设参数：展示各 agent 配置与 loop 预算
- 输入框：进入需求输入与预处理
- 模块架构图：展示 workspace 里的架构树

菜单：

- 1-输入：录入需求，生成预处理输出
- 2-日志：查看最近日志
- 3-参数：配置 agent 参数与 API Key
- 4-退出：退出 TUI

## 配置与安全

- 配置文件：data/config/agent-config.json
- 密钥目录：data/config/keys/
- API Key 必须通过 TUI 输入，不从 .env 读取
- 加密流程：Kyber KEM -> HKDF(SHA-256) -> AES-GCM

## 数据来源与输出

- 任务列表：data/workspace/tasks.json
- 架构图：data/workspace/architecture.txt 或 data/workspace/architecture.json
- 预处理输出：data/workspace/preprocess/<request_id>.json

## 测试与演示

- 运行测试：python3 app/ui/test_tui.py
- 演示仪表盘：python3 app/ui/demo_tui.py

## 开发者提醒：依赖变更与镜像重建

用户使用 `setup.py` 时不会感知依赖问题，但开发者修改 `requirements.txt` 后必须触发镜像构建，否则容器仍会沿用旧依赖。

- `setup.py` 会检测 `requirements.txt` 变化并自动 `build agent-core`
- 若手动操作，请执行：
	- `docker compose build agent-core`
	- `docker compose up -d`

