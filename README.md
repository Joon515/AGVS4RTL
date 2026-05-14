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

### 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（LLM 密钥等）
cp .env.example .env
# 编辑 .env，至少设置 AGVS4RTL_LLM_ENABLED / AGVS4RTL_LLM_BASE_URL / AGVS4RTL_LLM_API_KEY

# 3. 语法校验（快速检查，不依赖 Docker）
python -m compileall src

# 4. 构建并启动三服务
docker compose up -d --build

# 5. 健康检查
curl http://localhost:8001/health
```

---

### 当前能力

系统已完成 **Parser → Generator → Verify → Archive** 最小闭环，可通过 HTTP API 端到端运行：

| 能力 | 状态 |
| :--- | :--- |
| **意图解析与任务编排** | Parser 接收自然语言需求，生成结构化 `UserTaskSpec`，通过 LangGraph 状态机调度 Gen / Verify |
| **RTL 代码生成** | Generator 产出结构化 `SpecReg` 与多文件 Verilog（含层级子模块），支持规则化生成与 LLM 驱动两种模式 |
| **静态验证** | Verify 执行 Spec 存在性、端口方向/位宽一致性、`iverilog` 编译检查，输出 `PASS / FAIL_SEMANTIC / FAIL_COMPILE / INFRA_ERROR` |
| **失败注入与重试闭环** | 5 条 retry 路径（COMPILE / SEMANTIC / INFRA / PORT_DIRECTION / PORT_WIDTH）已通过集成测试，6/6 通过 |
| **动态仿真** | `simulate_node` 支持 LLM 驱动自动生成 cocotb testbench + Makefile，可选执行仿真 |
| **超时治理** | Parser 对 Verify 可配超时（默认 240s），通过 `VerifyStatus` 状态文件实现超时后自动恢复 |
| **WebUI** | 前端提供任务提交、进度查看、结果归档等交互界面，支持异步提交流程 |

---

### 下一步

1. **静态契约核查增强**：补充时钟/复位映射检查、协议端口映射、跨模块接口一致性校验。
2. **动态仿真深化**：覆盖率驱动测试生成、VCD 波形分析、断言自动生成。
3. **LLM 差异化修复**：按失败类型（语义/编译/端口/位宽）实现不同的 LLM 修复策略。
4. **可观测性提升**：节点级耗时统计、任务级日志关联、失败现场保留策略。
5. **复杂模块支持**：当前规则化 Generator 对复杂处理器（如 rv32i）支持有限，需增强 LLM 驱动生成能力。

---

### 开发文档

| 文档 | 说明 |
| :--- | :--- |
| `DEVLOG.md` | 开发日志，按日期记录变更动机、内容与验证结果；含 Parser / Generator / Verify 三模块的正式行为定义 |
| `tests/README.md` | 集成测试的运行方式、分类标记与排错指南 |
| `.github/copilot-instructions.md` | 编码规范、架构约定与常见陷阱（Copilot 自动读取） |
