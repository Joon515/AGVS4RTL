# 2026-03-01 迭代总结（多模型接入与多轮输出追踪）

## 1. 本轮目标

本轮围绕以下目标推进：

1. 支持多模型、分角色协作（解析模型与代码模型解耦）。
2. 支持 OpenAI 兼容云端 API 接入并可快速切换模型。
3. 将工作流扩展到“需求解析 -> 架构设计 -> PPA -> Verilog 框架生成”。
4. 增加多轮输出追踪，保留每个阶段的输出历史。
5. 补齐可执行冒烟脚本，确保容器内一键验证。

---

## 2. 关键功能改动

### 2.1 统一 LLM 配置解析

新增统一配置解析模块，按优先级读取：
- 显式参数
- `data/config/agent-config.json`（含解密 `api_key_enc`）
- 环境变量

文件：
- [app/llm_config.py](app/llm_config.py)

影响：
- `ParserAgent`、`ArchitectAgent`、`CodegenAgent` 可统一读到 `model/api_base/api_key`。
- 解决了此前“默认模型覆盖配置模型”的问题。

### 2.2 双模型职责链路落地

职责分工：
- `pre_agent`（默认 DeepSeek Chat）负责自然语言解析与 JSON 化。
- `generate_agent`（先 DeepSeek Reasoner，后切到 Qwen3-Coder）负责 Verilog 框架生成。

新增/变更文件：
- [app/pre_agent/parser_agent.py](app/pre_agent/parser_agent.py)
- [app/manage_agent/architect_agent.py](app/manage_agent/architect_agent.py)
- [app/manage_agent/codegen_agent.py](app/manage_agent/codegen_agent.py)
- [app/manage_agent/__init__.py](app/manage_agent/__init__.py)

### 2.3 工作流扩展到 codegen

新增完整工作流：
- `create_full_codegen_workflow()`
- `run_full_codegen_workflow()`

节点顺序：
- parser -> architect -> ppa_estimator -> codegen

文件：
- [app/workflow.py](app/workflow.py)

### 2.4 多轮输出追踪（round_outputs）

新增状态字段：
- `generated_code`
- `round_outputs`

并在每个阶段节点追加记录：
- parser
- architect
- ppa_estimator
- codegen

文件：
- [app/manage_agent/state_schema.py](app/manage_agent/state_schema.py)
- [app/pre_agent/parser_agent.py](app/pre_agent/parser_agent.py)
- [app/manage_agent/architect_agent.py](app/manage_agent/architect_agent.py)
- [app/manage_agent/ppa_estimator.py](app/manage_agent/ppa_estimator.py)
- [app/manage_agent/codegen_agent.py](app/manage_agent/codegen_agent.py)

### 2.5 冒烟与行为探针脚本

新增脚本：
- 云端连通 + 多 Agent 冒烟：
  - [app/test_cloud_multiagent_smoke.py](app/test_cloud_multiagent_smoke.py)
- 双模型 codegen 冒烟：
  - [app/test_dual_model_codegen_smoke.py](app/test_dual_model_codegen_smoke.py)
- 模型行为探针（多模型对比）：
  - [app/model_behavior_probe.py](app/model_behavior_probe.py)

输出产物：
- [data/workspace/test_output/dual_model_codegen_smoke.json](data/workspace/test_output/dual_model_codegen_smoke.json)
- [data/workspace/test_output/dual_model_codegen_history.jsonl](data/workspace/test_output/dual_model_codegen_history.jsonl)
- [data/workspace/test_output/model_probe_ds_chat.json](data/workspace/test_output/model_probe_ds_chat.json)
- [data/workspace/test_output/model_probe_ds_reasoner.json](data/workspace/test_output/model_probe_ds_reasoner.json)

### 2.6 UI 包导入副作用修复

将 `TUIApp` 改为惰性导入，避免仅使用 `ConfigStore` 时触发不必要依赖链。

文件：
- [app/ui/__init__.py](app/ui/__init__.py)

---

## 3. 模型接入结果

### 3.1 DeepSeek 接入

已完成并验证：
- `pre_agent`: `deepseek-chat`
- `architecture_agent`: `deepseek-reasoner`

### 3.2 Qwen3-Coder 接入（SiliconFlow）

已完成并验证：
- `generate_agent`: `Qwen/Qwen3-Coder-480B-A35B-Instruct`
- 新增 `coder_agent`: `Qwen/Qwen3-Coder-480B-A35B-Instruct`
- `api_base`: `https://api.siliconflow.cn/v1`

配置文件更新：
- [data/config/agent-config.json](data/config/agent-config.json)

---

## 4. 验证记录（本轮）

1. `setup.py` 拉起容器成功，`agent-core`/`eda-sandbox` 正常运行。
2. 无 LLM 依赖单测 `app/pre_agent/test_unit_basic.py` 通过（8/8）。
3. 云端连通脚本可用，DeepSeek 与 SiliconFlow 均验证过最小请求。
4. 双模型 codegen 冒烟通过，`generated_code` 正常写入并带 `module`。
5. `round_outputs` 在输出 JSON 中可见，包含四阶段追踪。

---

## 5. 已知问题与处理

1. `architect` 阶段偶发 `Connection error`，当前会回退到 fallback 架构，不阻断流程。
2. `chromadb` 在部分容器中未安装，RAG 初始化会告警但不影响冒烟主链路。
3. 某些模型在特定平台可能返回 `Model does not exist`，需确保 `model + api_base` 匹配。

---

## 6. 产出状态

本轮已将仓库从“预处理+架构+PPA”推进到“可配置多模型 + 代码框架生成 + 多轮追踪 + 冒烟闭环”。

可直接用于后续：
- 在同一工作流中扩展测试生成、仿真验证、自动修复。
- 基于 `dual_model_codegen_history.jsonl` 做回归评估与模型效果比较。

---

## 7. 安全建议

本轮对话中曾出现明文 API Key。建议：
- 立即在对应平台轮换该 Key。
- 仅保留加密后的 `api_key_enc` 于配置文件。
- 避免在终端历史、日志、Issue 中写入明文凭据。

---

## 8. 本轮对话增量改进（4-Agent 一致性专项）

本节总结本轮对话中新增/调整的能力（在上文基础上的增量）。

### 8.1 工作流重构为 4 Agent 主链

主链从 `parser -> architect -> ppa_estimator -> codegen` 调整为：

- `NLP(parser) -> Architect -> Codegen -> Verify`

对应实现：
- 新增 `VerifyAgent`：
  - [app/manage_agent/verify_agent.py](app/manage_agent/verify_agent.py)
- 工作流编排更新：
  - [app/workflow.py](app/workflow.py)
- 导出接口补齐：
  - [app/manage_agent/__init__.py](app/manage_agent/__init__.py)

### 8.2 状态与追踪增强（用于一致性判定）

为支持“上游输出-下游输入完全一致”检查，新增/补齐：

- `verification` 状态字段：
  - [app/manage_agent/state_schema.py](app/manage_agent/state_schema.py)
- 原始输入字段透传（避免 verify 看到空需求）：
  - `natural_language` / `language` / `source`
  - [app/manage_agent/state_schema.py](app/manage_agent/state_schema.py)
  - [app/pre_agent/parser_agent.py](app/pre_agent/parser_agent.py)
- 每阶段 `round_outputs` 增加 `input_snapshot`：
  - [app/pre_agent/parser_agent.py](app/pre_agent/parser_agent.py)
  - [app/manage_agent/architect_agent.py](app/manage_agent/architect_agent.py)
  - [app/manage_agent/codegen_agent.py](app/manage_agent/codegen_agent.py)
  - [app/manage_agent/verify_agent.py](app/manage_agent/verify_agent.py)

### 8.3 一致性测试脚本体系

新增完整一致性冒烟脚本（在线/离线）：
- [app/test_four_agent_consistency_smoke.py](app/test_four_agent_consistency_smoke.py)

新增 MVP 版本（保留语义精度与 verify 打分，不考察后端实现完整性）：
- [app/test_four_agent_consistency_smoke_mvp.py](app/test_four_agent_consistency_smoke_mvp.py)

当前 MVP 判定项：
- `framework_minimal_valid`
- `nlp_json_high_alignment`
- `verify_score_gate`

### 8.4 默认样例切换为“8位乘法器”

本轮将常用 smoke/记录默认需求统一到“最简单的8位乘法器”，降低噪声并便于快速回归：

- [app/test_four_agent_consistency_smoke.py](app/test_four_agent_consistency_smoke.py)
- [app/test_dual_model_codegen_smoke.py](app/test_dual_model_codegen_smoke.py)
- [app/test_cloud_multiagent_smoke.py](app/test_cloud_multiagent_smoke.py)
- [app/generate_agent_round_records.py](app/generate_agent_round_records.py)
- [app/model_behavior_probe.py](app/model_behavior_probe.py)

### 8.5 单 Agent 记录不更新问题修复

定位结论：
- 记录脚本在线模式在模型调用阶段可能阻塞，导致“未执行到落盘”。

修复措施：
- 为记录脚本新增 `--result-json` 离线输入模式，保证可稳定生成记录：
  - [app/generate_agent_round_records.py](app/generate_agent_round_records.py)

验证：
- 记录目录已产生新批次文件与 manifest（四个 Agent 子目录均更新）。

### 8.6 本轮验证结论（8位乘法器）

- 标准一致性脚本（非 MVP）可跑通，但更严格门槛下可能因 verify 分数/功能细节而不通过。
- MVP 脚本已通过：
  - [data/workspace/test_output/four_agent_consistency_smoke_mvp_8bit.json](data/workspace/test_output/four_agent_consistency_smoke_mvp_8bit.json)
  - `overall_pass = true`

### 8.7 下一步建议

1. 将 `test_four_agent_consistency_smoke_mvp.py` 作为默认回归入口（CI 第一层）。
2. 将严格版一致性脚本保留为夜间/发布前质量门（CI 第二层）。
3. 后续再逐步提高 `verify_score_gate` 阈值，避免一次性引入过高门槛。
