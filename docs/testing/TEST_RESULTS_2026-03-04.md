# AGVS4RTL TestAgent 阶段开发测试报告

**日期**: 2026-03-04  
**测试范围**: TestAgent、Manager→Test 工作流、Sandbox Verilator/pyuvm 执行、覆盖率回写、API 配置连通性  
**测试环境**: Docker (`hdl_agent_core`, `hdl_sandbox`)

---

## 执行摘要

✅ **本阶段核心目标已完成**：

- TestAgent 从“静态模板生成”升级为“可执行仿真链路”
- `state.tests/state.coverage/state.errors` 全链路回写验证通过
- 覆盖率从占位值升级为真实产物解析（`coverage.dat` → `lcov info`）
- 配置与模型验证完成：`Pro/zai-org/GLM-4.7` 实测可用

---

## 交付清单

### 新增文件

- `app/test_agent/__init__.py`
- `app/test_agent/test_agent.py`
- `app/test_agent/test_unit_basic.py`
- `app/dev_tests/run_test_agent_docker_integration.py`

### 变更文件

- `app/workflow.py`（新增 `test_generator` 节点）
- `deploy/sandbox.Dockerfile`（固定 cocotb 兼容版本）
- `data/config/agent-config.json`（切换模型到 GLM-4.7）

---

## 测试结果

### ✅ Test 1：TestAgent 单元测试（无 Sandbox 依赖）

**命令**

```bash
docker compose exec -T agent-core python3 - <<'PY'
from pathlib import Path
import tempfile
from app.test_agent.test_unit_basic import test_test_agent_generates_templates_and_state

tmpdir = Path(tempfile.mkdtemp(prefix='agvs_test_agent_unit_'))
test_test_agent_generates_templates_and_state(tmpdir)
print('unit ok', tmpdir)
PY
```

**结果**

- 输出 `unit ok ...`
- 通过

---

### ✅ Test 2：Docker 集成测试（Verilator + pyuvm）

**命令**

```bash
timeout 300s docker compose exec -T agent-core python3 app/dev_tests/run_test_agent_docker_integration.py
```

**结果摘要**

- `demo_top.execution_status = pass`
- `demo_leaf.execution_status = pass`
- `errors = []`
- `coverage.status = pass`

---

### ✅ Test 3：覆盖率真实产物解析

**验证链路**

1. Verilator 以覆盖率参数编译执行
2. 生成 `coverage.dat`
3. `verilator_coverage --write-info` 生成 `.info`
4. TestAgent 解析 `.info` 与 `*_results.xml`，回写 `state.coverage`

**结果**

- 代码覆盖率字段不再使用固定占位
- 本轮示例中 `line/branch/fsm_state = 100.0`

---

### ✅ Test 4：加密 API Key 与模型连通性

**输入**

- 使用配置中的 `api_key_enc`（`key_id = RSscnjC4iDgA`）
- API Base: `https://api.siliconflow.cn/v1`

**结果**

- `decrypt_ok = True`
- `models.list()` 调用成功
- `Qwen/Qwen3-Coder-480B-A35B-Instruct` 返回服务端 `500(code=60009)`（供应端异常）
- `Qwen/Qwen2.5-7B-Instruct` 调用成功
- `Pro/zai-org/GLM-4.7` 调用成功，回复 `GLM47_OK`

---

## 关键问题与修复

### 问题 1：cocotb 2.x 与当前 Verilator 组合不兼容

**现象**

- `verilator.cpp` 编译报错（`VerilatedVpi::*` 接口不匹配）

**修复**

- Sandbox 镜像固定版本：
  - `cocotb==1.8.1`
  - `cocotb-test==0.2.5`

---

### 问题 2：运行参数导致仿真失败

**现象**

- `Unknown runtime argument: +verilator+coverage+file+...`

**修复**

- 移除不受支持的 plus-args
- 使用 `sim_build` 定位构建目录
- 从标准位置读取 `coverage.dat` 并转换为 `.info`

---

## 状态回写验证

### `state.tests`

- 每个模块包含 `status/test_file/framework/test_cases/execution_status/simulation_report`

### `state.coverage`

- 顶层：`version/generated_at/status/thresholds/reports/notes`
- 子项：`reports[].code_coverage/functional_coverage/assertion_coverage/status`

### `state.errors`

- 仿真失败时写入 `functional_error` 或 `environment_error`

---

## 已知限制

1. `functional_coverage` 当前由 `*_results.xml` 的测试通过率映射得到（近似值）
2. `assertion_coverage` 仍为占位（未接入 SVA/断言统计）
3. 覆盖率阈值告警仅写入 `notes`，尚未触发自动重试策略

---

## 结论

本次 TestAgent 阶段完成了从“生成测试代码”到“真实容器仿真执行与覆盖率回写”的端到端能力，满足当前开发目标，可进入下一步 Analyzer 深化与策略重试联动。
