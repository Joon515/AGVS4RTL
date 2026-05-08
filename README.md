# AGVS4RTL Remake Project

AGVS4RTL 是一个面向 RTL 自动生成与验证的多 Agent 系统。

---

### 系统架构设计

系统采用基于 FastAPI 的三服务协同架构，Parser 作为统一入口对外提供 API，Generator 与 Verify 仅在容器内部网络中提供服务。

1. **Parser**: 负责意图解析、任务拆解与全局状态编排。
2. **Generator**: 包含 Architect 与 Coding 两个子节点，内部基于 LangGraph 维持局部状态机，将抽象需求按图结构 (Graph) 逐步细化为 RTL 代码实现。
3. **Verify**: 负责执行从静态语义核查到动态仿真的全闭环验证，生成逻辑不依赖验证环境，验证逻辑仅依赖生成的 Spec 契约。
4. **Data Plane**: 基于 `Shared Workspace` 物理挂载项目开发文件，动态配置 Agent 读取权限，实现标准化文件参考。
5. **Container Topology**: 运行时仅保留 `parser`、`gen`、`verify` 三个容器；`parser` 暴露宿主机端口，`gen` 与 `verify` 只通过 Docker 内部网络被访问。

### 技术栈选择

| 维度 | 选型 | 作用 |
| :--- | :--- | :--- |
| **基础运行环境** | Python 3.11 + Docker | 确保跨平台的一致性与隔离性 |
| **包管理** | **pip + requirements.txt** | 使用标准依赖清单，便于环境复现与镜像构建 |
| **任务调度** | **LangGraph + FastAPI** | 基于 LangGraph 原生支持的 Checkpoint 实现状态机，FastAPI 包装服务流转数据 |
| **Agent 编排** | **LangGraph** | 管理网状非线性逻辑，支持 Checkpoint 状态持久化 |
| **意图路由** | **Semantic Router** | 极速语义过滤，降低 LLM 调用开销 |
| **协议约束** | **Pydantic v2** | 定义强类型 JSON 协议，防止跨节点数据漂移 |
| **硬件验证** | **Cocotb + iverilog** | 基于 Python 的测试激励驱动与轻量级仿真 |

---

### 项目目录结构

```Plaintext
AGVS4RTL/
├── docker/                  # Docker 配置文件
│   ├── Dockerfile.parser    # Parser 镜像
│   ├── Dockerfile.gen       # Architect-Coding 镜像
│   └── Dockerfile.verify    # Verify 镜像 (集成 iverilog/Cocotb)
├── src/                     # 业务源代码
│   ├── common/              # Pydantic 协议模型与跨服务共享类型
│   ├── parser/              # Parser Agent 逻辑 (LangGraph Nodes)
│   ├── generator/           # 代码生成逻辑 (Architect & Coding)
│   └── verify/              # 验证逻辑 (Static Check & Dynamic Sim)
├── shared_workspace/        # 容器共享工作区 (挂载卷)
│   ├── specs/               # 结构化 Spec-Registry (JSON/YAML)
│   ├── rtl/                 # 生成的 Verilog 源码
│   └── sim/                 # 仿真产物 (VCD 波形, Log)
├── docker-compose.yml       # 三容器编排 (仅 parser 对外暴露)
├── requirements.txt         # Python 依赖定义
└── .env                     # 权限与密钥环境变量
```

---

### 未来改进项目

1. ~~引入失败注入测试与重试闭环验收~~ **（已完成）**。当前 retry 路径（FAIL_COMPILE、FAIL_SEMANTIC、INFRA_ERROR、PORT_DIRECTION、PORT_WIDTH）已通过集成测试验证，6/6 全部通过。

2. 继续增强 Verify 的**静态契约核查粒度**。当前已实现端口方向、位宽等核查，后续可补充时钟/复位映射核查、协议端口映射、跨模块接口一致性校验等。

3. 扩展 Verify 的**动态仿真能力**。当前已实现 cocotb testbench 自动生成（LLM 驱动）与 `simulate_node`，后续可补充覆盖率驱动测试生成、VCD 波形分析、断言自动生成等。

4. 强化 Generator 的**多轮 LLM 修复利用能力**。当前规则化修复已验证，但 LLM 驱动按失败类型（语义/编译/端口/位宽）的差异化修复策略仍未实现。

5. 补充**工作流异常治理与可观测性**。当前已补充 Verify 状态文件机制、Parser 超时自动恢复、ParserChat 日志；后续可增加节点级耗时统计、任务级日志关联、失败现场保留策略。

---

### 最新开发进度

1. 完成 `src/common/models.py` 的大规模协议扩展：新增 `verify_rpt_path`、`source_file`、`testbench_path/makefile_path`、`rtl_paths` 等字段，以及 5 个注入标记常量。

2. 完成 LLM 工具函数去重：创建 `src/common/llm_utils.py`，提取 `_chat_completions_url` 等函数及 LLM Header 常量；修复 N1（未定义 logger）和 N2（content.strip 不一致）两个 bug。

3. 完成 B4 重试闭环与多文件 HDL 生成：Parser 显式传递 `verify_rpt_path`；Generator 新增 `_apply_fix_from_verify_rpt()` 消费验证报告执行规则化修复；`finalize_node` 支持多文件 .v 输出。

4. 完成 B5 Cocotb 测试区生成：创建 `src/verify/simulate.py`，支持 LLM 驱动生成 cocotb testbench + 规则生成 Makefile；Verify 工作流新增 `simulate_node`。

5. 完成 Verify 超时治理：Parser 对 Verify 超时 20s → 240s（可配）；Verify 写 `VerifyStatus` 状态文件；Parser 超时后通过状态文件判断并自动恢复已完成结果。

6. 完成基础设施清理：修复 Dockerfile Git 合并冲突；标准化 `__init__.py`；去重 `HealthStatus`；修正 `.gitignore` 笔误；LLM 不可用时 Generator 抛明确错误。

7. 集成测试验证：`test_host_workflow.py` 6/6 全部通过（含 retry 闭环）；`test_fuzzy_requirement_workflow.py` 251s 完成；层级 HDL 多文件生成通过；cocotb testbench 生成通过。