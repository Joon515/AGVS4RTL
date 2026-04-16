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

1. 引入 **最小 Verify Stub**。当前系统已完成 Parser + Generator 的最小闭环，下一阶段最重要的是补上一个最小可运行的 Verify 模块，先完成文件存在性检查与可选的 `iverilog` 编译校验，使系统从“能生成”提升到“能做最小验证”。

2. 恢复 Parser 的 **完整工作流编排**。在 Verify Stub 可用后，将当前简化状态机重新扩展为 `parser_initialize -> gen_stateless -> verify_stateless -> route -> archive`，重新接入验证后路由与后续失败处理逻辑。

3. 固化 **VerifyRpt 落盘约定**。Generator 已预留重试轮次读取上一轮 `VerifyRpt` 的逻辑，但上游尚未稳定写入对应文件。下一阶段需要统一 Verify 报告的目录、命名与迭代版本规则，确保后续修复闭环可以真实落地。

---

### 最新开发进度

1. 已完成 `src/common/models.py` 的第一轮稳定化重构，统一了 Parser / Generator 当前阶段使用的核心协议模型，并修复了 `strict=True` 导致 FastAPI 枚举字段跨服务传输失败的问题。  
2. 已完成 Parser 工作流的最小闭环改造，当前状态机收缩为 `parser_initialize -> gen_stateless -> archive_success`，可稳定完成任务初始化、`UserTaskSpec` 落盘、Generator 调度与结果归档。  
3. 已完成 Generator 内部 LangGraph 骨架重构，形成 `init_context -> architect -> coder -> finalize` 四节点流程，并在**不依赖 LLM 接口**的情况下实现基于规则占位的 `SpecReg` 与 Verilog RTL 生成。  
4. 已完成 Docker 三服务联调与宿主机入口确认：当前 Parser 对外映射端口为 `8001`，Generator / Verify 保持仅容器内可见，符合既定三容器网络隔离设计。  
5. 已成功跑通首个 Parser + Generator 端到端样例，系统可返回 `WorkflowRunResult(success=true)`，并在 `Output/TASK_ID/Result/shared_workspace/` 下产出 `UserTaskSpec.json`、`SpecReg_iter0.json` 与 `{top_module}.v`。