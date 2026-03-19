# AGVS4RTL Remake Project

AGVS4RTL 是一个面向 RTL 自动生成与验证的多 Agent 系统。
该分支 (`r05en_remake`) 专注于全系统重构，旨在消除非线性协作导致的“代码史山”，建立稳固的工程化底座。

---

### 系统架构设计

系统采用基于智能体自主管理消息队列的协同架构，通过消息队列实现 Agent 间的异步协作与任务路由。

1. **Parser**: 负责意图解析、任务拆解与全局状态编排。
2. **Generator**: 包含 Architect 与 Coding 两个子节点，负责从 Spec 生成到 RTL 代码实现。
3. **Verify**: 负责执行从静态语义核查到动态仿真的全闭环验证，生成逻辑不依赖验证环境，验证逻辑仅依赖生成的 Spec 契约。
4. **Data Plane**: 基于 `Shared Workspace` 物理挂载项目开发文件，动态配置 Agent 读取权限，实现标准化文件参考。

### 技术栈选择

| 维度 | 选型 | 作用 |
| :--- | :--- | :--- |
| **基础运行环境** | Python 3.11 + Docker | 确保跨平台的一致性与隔离性 |
| **包管理** | **uv** | 高性能依赖同步，确保各镜像版本严格一致 |
| **任务调度** | **Celery + Redis** | 异步处理长耗时 RTL 任务，支持重试与状态监控 |
| **Agent 编排** | **LangGraph** | 管理网状非线性逻辑，支持 Checkpoint 状态持久化 |
| **意图路由** | **Semantic Router** | 极速语义过滤，降低 LLM 调用开销 |
| **协议约束** | **Pydantic v2** | 定义强类型 JSON 协议，防止跨节点数据漂移 |
| **硬件验证** | **Cocotb + iverilog** | 基于 Python 的测试激励驱动与轻量级仿真 |

---

### 项目目录结构

```Plaintext
AGVS4RTL/
├── docker/                  # Docker 配置文件
│   ├── Dockerfile.base      # 统一基础镜像 (uv-based)
│   ├── Dockerfile.parser    # Parser 镜像
│   ├── Dockerfile.gen       # Architect-Coding 镜像
│   └── Dockerfile.verify    # Verify 镜像 (集成 iverilog/Cocotb)
├── src/                     # 业务源代码
│   ├── common/              # Pydantic 协议、Celery App 配置、共享 Utils
│   ├── parser/              # Parser Agent 逻辑 (LangGraph Nodes)
│   ├── generator/           # 代码生成逻辑 (Architect & Coding)
│   └── verify/              # 验证逻辑 (Static Check & Dynamic Sim)
├── shared_workspace/        # 容器共享工作区 (挂载卷)
│   ├── specs/               # 结构化 Spec-Registry (JSON/YAML)
│   ├── rtl/                 # 生成的 Verilog 源码
│   └── sim/                 # 仿真产物 (VCD 波形, Log)
├── docker-compose.yml       # 多容器编排
├── pyproject.toml           # 项目依赖定义
└── .env                     # 权限与密钥环境变量
```

---

### 本次重构计划改进

1. 引入 **Verify-Coding 反馈回路**。系统优先进行语义空跑（Dry-run），通过后再启动基于 Icarus Verilog 的动态仿真，大幅提升无效生成的纠错效率。
2. Architect 不再产生模糊描述，而是输出 **Spec-Registry (规格注册表)**。通过 Pydantic 强类型约束端口定义与协议，从源头解决接口不匹配问题。
3. 通过 `.env` 注入 `USER_ID/GROUP_ID`，确保 Docker 容器内生成文件与宿主机权限对齐，消除跨容器读写障碍。
4. 使用 Celery 队列隔离不同算力需求的任务，支持任务在多 Agent 间的非线性流转。

---

### 本次 Commit（26/03/19 8:45）进度

大幅度简化重构了模块架构和功能，明确了系统I/O控制方法：
1. 重新分配智能体 Docker 架构，摒弃原 Parser Docker 的中心化调用，采用基于消息队列的事件分发。三大核心组件各自认领并维护专属的数据契约，实现高度解耦。
2. 明确文档常态为只读增量状态，在触发全局重构前，所有 Agent 对 SharedWorkspace 中的文档仅做“增量追加”，绝不覆盖原文件，保留完整的迭代溯源能力。
3. 追加大文本物理隔离措施，将用户输入的自然语言 Prompt 以及仿真日志直接落盘到 `shared_workspace` 缓存区，Celery 消息总线上仅传输轻量级的 JSON 指针和状态码。
4. 统一了系统的 I/O 控制方法，Gen 和 Verify 容器在沙盒（缓存区）内闭环工作，最终资产的物理搬运由 Parser 作为 I/O 控制器统一执行。

同时定义了四大核心 Pydantic 模型，严格约束跨容器通信：
1. `BaseSyncMeta` (公共消息头)
- **功能**: 分布式调用链追踪。
- **核心字段**: 全局唯一的 `task_id`，当前 `iteration`（迭代轮次），`refactor_label`（重构级别），以及 `intent`（生成/测试/修复等核心意图）。
2. `UserTaskSpec` (用户任务规约) - *Parser 持有*
- **功能**: 下发给全网的标准化研发工单。
- **核心字段**: 
  - 提炼后的需求与红线约束 (`refined_requirements`, `design_rules`)。
  - 沙盒工作区路由 (`workspace_dir`, `external_target_path`)。
3. `SpecReg` (规格注册表) - *Gen Docker 产出*
- **功能**: Architect 生成的强类型硬件施工蓝图。
- **核心字段**: 
  - 严格枚举的端口列表（`PortDef`，包含方向、类型、参数化位宽）。
  - 时钟域与复位映射 (`clock_and_reset`)。
  - 验证容器可直接调用的标准协议编组 (`ProtocolGroup`)。
4. `VerifyRpt` (验证报告) - *Verify Docker 产出*
- **功能**: 带有现场证据的诊断判决书。
- **核心字段**: 
  - 细粒度判决状态（`PASS`, `FAIL_SEMANTIC`, `FAIL_COMPILE`, `FAIL_SIMULATION`）。
  - 错误快照（`ErrorSnapshot`），精准提取接口 Mismatch 和报错行号，拒绝大文本刷屏。

---

### 其余待办事项

- 目前为了调试方便采用 `chmod 777`，后期需细化 `shared_workspace` 的读写控制。
- 需完成节点内部的逻辑搭建。
- 定义各 Worker 内部的具体任务函数，接入 LLM API。