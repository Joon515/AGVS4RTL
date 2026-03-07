# AGVS4RTL

AGVS4RTL 是一个面向 RTL 自动生成与一致性验证的多 Agent 系统。
当前仓库已具备从自然语言需求到 Verilog 框架代码、再到一致性评估的可执行链路，并提供 TUI 与 Docker 化运行环境。

## 核心能力

- 预处理数据结构：标准化自然语言需求与约束输出
- Rich TUI 仪表盘：日志入口、输入框、任务列表、参数配置、模块架构图
- Agent 配置中心：每个 agent 的模型参数与 loop 预算
- API Key 强制 TUI 输入并使用 RSA-OAEP + AES-GCM 混合加密存储

## 工作流概览

```text
用户需求(自然语言)
		↓
Parser Agent（意图/约束抽取）
		↓
Architect Agent（架构分层与端口定义，支持RAG）
		↓
Codegen Agent（生成Verilog框架）
		↓
Verify Agent（需求-代码一致性评分）
		↓
输出: intent/constraints/architecture/generated_code/verification/round_outputs
```

## 目录导航

- `app/main.py`：应用入口（默认启动 TUI）
- `app/workflow.py`：工作流定义与执行入口
- `app/pre_agent/`：需求解析与预处理
- `app/manage_agent/`：架构、PPA、代码生成、一致性验证
- `app/rag/`：向量库与检索封装
- `app/ui/`：Rich TUI 与配置存储
- `data/config/`：Agent 配置与加密密钥
- `data/workspace/test_output/`：冒烟测试输出
- `docs/`：架构、规范、测试与迭代文档

## 快速开始

### 1) 依赖安装（本地）

```bash
pip install -r requirements.txt
```

### 2) 容器启动（推荐）

```bash
python3 setup.py
```

或手动执行：

```bash
docker compose build agent-core eda-sandbox
docker compose up -d
```

### 3) 启动 TUI

```bash
python3 -m app.main
```

## 配置说明

- 配置文件：`data/config/agent-config.json`
- 密钥目录：`data/config/keys/`
- 统一配置解析：`app/llm_config.py`
	- 优先级：显式参数 > 配置文件 > 环境变量

### API Key 加密机制（当前实现）

`app/ui/config_store.py` 采用混合加密：

- 使用 AES-GCM 加密 API Key 明文
- 使用 RSA-OAEP 加密 AES 会话密钥

> 注：当前实现为 RSA + AES-GCM；并非 PQC KEM。

## 运行与测试

### A. 预处理基础单测（容器）

```bash
docker compose exec agent-core python3 app/pre_agent/test_unit_basic.py
```

### B. 4-Agent 一致性冒烟（MVP，推荐日常回归）

```bash
docker exec -e PYTHONPATH=/app hdl_agent_core sh -lc \
"python3 /app/app/test_four_agent_consistency_smoke_mvp.py \
	--case '设计一个最简单的8位乘法器。' \
	--output /app/data/workspace/test_output/four_agent_consistency_smoke_mvp_8bit.json"
```

### C. 4-Agent 一致性冒烟（严格版）

```bash
docker exec -e PYTHONPATH=/app hdl_agent_core sh -lc \
"python3 /app/app/test_four_agent_consistency_smoke.py \
	--case '设计一个最简单的8位乘法器。'"
```

## 常见输出位置

- 测试报告：`data/workspace/test_output/`
- 多轮记录：`data/workspace/agent_round_records/`
- 预处理输出：`data/workspace/preprocess/`

## 相关文档

- `docs/development/2026-03-01-iteration-summary.md`
- `docs/architecture/state-schema.md`
- `docs/spec/ports-and-hierarchy.md`
- `docs/spec/agent-config.md`
- `docs/testing/docker-unit-tests.md`

## 现状与建议

- 已具备可执行主链与冒烟闭环，适合持续迭代模型与提示词。
- 建议将 MVP 一致性测试作为 CI 第一层门禁，严格版作为夜间或发布前门禁。

