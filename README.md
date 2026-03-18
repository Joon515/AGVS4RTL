# AGVS4RTL Remake Project

AGVS4RTL 是一个面向 RTL 自动生成与验证的多 Agent 系统。
该分支 (`r05en_remake`) 专注于全系统重构，旨在消除非线性协作导致的“代码史山”，建立稳固的工程化底座。

---

### 系统架构设计

系统采用**解耦的网状架构**，通过消息队列实现 Agent 间的异步协作与任务路由。

1. **Parser**: 负责意图解析、任务拆解与全局状态编排。
2. **Generator**: 包含 Architect 与 Coding 两个子节点，负责从 Spec 生成到 RTL 代码实现。
3. **Verify**: 负责执行从静态语义核查到动态仿真的全闭环验证，生成逻辑不依赖验证环境，验证逻辑仅依赖生成的 Spec 契约。
4. **Data Plane**: 基于 `Shared Workspace` 物理挂载统一文件参考，动态配置 Agent 读取权限，实现标准化文件参考。

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

### 本次 Commit（26/03/19 0:37）进度

1. 容器构建：基于uv构建了底层统一的三容器架构并基于redis成功连接各Agent。
2. 队列划分：每个worker分别监听了对应的任务队列（*workername*_queue）。
3. 环境细节：三容器在src内使用独立的worker安排任务，同时可在share_workspace内读取有关文档。

---

### 其余待办事项

- 目前为了调试方便采用 `chmod 777`，后期需细化 `shared_workspace` 的读写控制。
- 需完成 `src/common/models.py` 中的核心通信模型定义。
- 定义各 Worker 内部的具体任务函数，接入 LLM API。