from __future__ import annotations

import operator
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from src.common.models import (
    ClockResetDef,
    EndpointRef,
    GenNodeOutput,
    NodeType,
    PortDef,
    PortDirection,
    ResetType,
    RtlEdge,
    RtlNode,
    SpecReg,
    UserTaskSpec,
    VerifyRpt,
    WorkTaskPayload,
)


class GenWorkflowState(TypedDict):
    """
    Generator 内部 LangGraph 状态。

    说明：
    - task: Parser 下发的轻量任务载荷
    - iteration: 当前生成轮次
    - messages: 预留给后续 LLM 的多轮上下文
    - user_task_spec: 从文件中读取的用户结构化需求
    - verify_rpt: 若为重试轮次，则尝试加载上一轮验证报告
    - previous_spec_reg: 若为重试轮次，则尝试加载上一轮 SpecReg
    - spec_reg: 本轮生成的结构化设计契约
    - rtl_code: 本轮生成的 RTL 代码
    - gen_output: 最终输出载荷
    """
    task: WorkTaskPayload
    iteration: int
    messages: Annotated[List[Any], operator.add]
    user_task_spec: Optional[UserTaskSpec]
    verify_rpt: Optional[VerifyRpt]
    previous_spec_reg: Optional[SpecReg]
    spec_reg: Optional[SpecReg]
    rtl_code: Optional[str]
    gen_output: Optional[GenNodeOutput]


def _load_user_task_spec(task: WorkTaskPayload) -> UserTaskSpec:
    """
    从 Parser 提供的 spec_file_path 中加载 UserTaskSpec。
    """
    user_task_spec_path = Path(task.spec_file_path)
    if not user_task_spec_path.exists():
        raise FileNotFoundError(f"UserTaskSpec not found at {user_task_spec_path}")

    return UserTaskSpec.model_validate_json(user_task_spec_path.read_text(encoding="utf-8"))


def _load_previous_spec_reg(shared_task_dir: Path, previous_iteration: int) -> Optional[SpecReg]:
    """
    尝试加载上一轮 SpecReg。

    规则：
    - 路径约定为 shared_workspace/TASK_ID/specs/SpecReg_iter{n}.json
    - 若文件不存在，则返回 None
    """
    prev_spec_path = shared_task_dir / "specs" / f"SpecReg_iter{previous_iteration}.json"
    if not prev_spec_path.exists():
        return None

    return SpecReg.model_validate_json(prev_spec_path.read_text(encoding="utf-8"))


def _load_previous_verify_rpt(shared_task_dir: Path, previous_iteration: int) -> Optional[VerifyRpt]:
    """
    尝试加载上一轮 VerifyRpt。

    当前约定路径：
    - shared_workspace/TASK_ID/sim/VerifyRpt_iter{n}.json

    注意：
    - 该文件是否存在，取决于 Verify 服务以及 Parser 编排器是否按约定落盘。
    - 若文件缺失，Generator 应保持可运行，不直接失败。
    """
    verify_rpt_path = shared_task_dir / "sim" / f"VerifyRpt_iter{previous_iteration}.json"
    if not verify_rpt_path.exists():
        return None

    return VerifyRpt.model_validate_json(verify_rpt_path.read_text(encoding="utf-8"))


def _build_system_messages(
    task: WorkTaskPayload,
    user_task_spec: UserTaskSpec,
    previous_spec_reg: Optional[SpecReg],
    verify_rpt: Optional[VerifyRpt],
) -> List[Dict[str, str]]:
    """
    构造供后续 LLM 使用的对话上下文。

    当前即便尚未接入 LLM，也提前统一维护 messages 结构，
    便于后续直接替换 architect/coder 内部实现。
    """
    messages: List[Dict[str, str]] = []

    system_prompt = f"""You are an expert RTL architect and coding assistant.
Your task is to generate a correct SpecReg and Verilog RTL implementation.

Top module: {task.top_module}
Intent: {task.intent}
Iteration: {task.iteration}

Refined requirements:
{user_task_spec.refined_requirements}

Design rules:
{user_task_spec.design_rules}
"""
    messages.append({"role": "system", "content": system_prompt})

    if previous_spec_reg is not None:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Previous SpecReg from last iteration:\n"
                    f"{previous_spec_reg.model_dump_json(indent=2)}"
                ),
            }
        )

    if verify_rpt is not None:
        messages.append(
            {
                "role": "user",
                "content": (
                    "Previous verification failed. Here is the verification report:\n"
                    f"{verify_rpt.model_dump_json(indent=2)}"
                ),
            }
        )
    elif task.iteration > 0:
        messages.append(
            {
                "role": "user",
                "content": (
                    "Previous iteration failed, but verification report is missing. "
                    "Please re-evaluate the previous design and regenerate a safer implementation."
                ),
            }
        )

    return messages


def _derive_ports_from_task_spec(task: WorkTaskPayload, user_task_spec: UserTaskSpec) -> List[PortDef]:
    """
    依据当前 MVP 规则生成顶层端口列表。

    当前实现目标：
    - 先保证最小闭环可跑通
    - 默认生成一个简单时序模块接口
    - 后续可替换为真正的 LLM / 规则提取逻辑

    当前约定接口：
    - i_clk: 时钟
    - i_rst_n: 低有效异步复位
    - o_done: 输出完成信号
    """
    return [
        PortDef(
            name="i_clk",
            direction=PortDirection.INPUT,
            width="1",
            clock_domain="i_clk",
            is_clock=True,
            description="Primary clock input",
        ),
        PortDef(
            name="i_rst_n",
            direction=PortDirection.INPUT,
            width="1",
            clock_domain="i_clk",
            is_reset=True,
            description="Active-low asynchronous reset",
        ),
        PortDef(
            name="o_done",
            direction=PortDirection.OUTPUT,
            width="1",
            clock_domain="i_clk",
            description="Done flag output",
        ),
    ]


def _derive_nodes(task: WorkTaskPayload, verify_rpt: Optional[VerifyRpt]) -> List[RtlNode]:
    """
    生成架构节点列表。

    当前实现：
    - 统一生成一个最小可运行的叶子时序节点
    - 若后续需要更复杂架构，可在此接入 LLM 或规则引擎
    """
    description = "Sequential leaf logic that drives o_done with reset-safe behavior"

    if verify_rpt is not None and verify_rpt.requires_code_rewrite():
        description += "; regenerated after code-level verification failure"
    elif verify_rpt is not None and verify_rpt.requires_arch_refactor():
        description += "; regenerated after architecture-level verification failure"

    return [
        RtlNode(
            node_id="seq_done_logic",
            node_type=NodeType.SEQUENTIAL,
            description=description,
            is_leaf=True,
        )
    ]


def _derive_edges() -> List[RtlEdge]:
    """
    生成最小图结构连线。

    注意：
    - 当前 models.py 中 RtlEdge.source/target 必须使用 EndpointRef，而不是字符串。
    """
    return [
        RtlEdge(
            source=EndpointRef(node_id="TOP", port_name="i_clk"),
            target=EndpointRef(node_id="seq_done_logic", port_name="clk"),
            signal_name="i_clk",
            width="1",
            description="Clock connection",
        ),
        RtlEdge(
            source=EndpointRef(node_id="TOP", port_name="i_rst_n"),
            target=EndpointRef(node_id="seq_done_logic", port_name="rst_n"),
            signal_name="i_rst_n",
            width="1",
            description="Reset connection",
        ),
        RtlEdge(
            source=EndpointRef(node_id="seq_done_logic", port_name="q"),
            target=EndpointRef(node_id="TOP", port_name="o_done"),
            signal_name="o_done",
            width="1",
            description="Done output connection",
        ),
    ]


def _build_dummy_spec_reg(
    task: WorkTaskPayload,
    user_task_spec: UserTaskSpec,
    verify_rpt: Optional[VerifyRpt],
) -> SpecReg:
    """
    当前版本的 SpecReg 生成实现。

    说明：
    - 这是 Architect 节点的规则化/占位实现。
    - 目标不是最终智能架构推理，而是先产生严格符合当前模型约束的 SpecReg。
    - 后续接入 LLM 时，可直接替换此函数内部逻辑，但输出结构应保持一致。
    """
    module_description = f"Automated SpecReg for {task.top_module}"

    if verify_rpt is not None:
        module_description += f" regenerated after {verify_rpt.verdict}"

    return SpecReg(
        task_id=task.task_id,
        iteration=task.iteration,
        intent=task.intent,
        top_module=task.top_module,
        module_description=module_description,
        verification_directives=[
            "Check reset behavior on i_rst_n",
            "Check that o_done deasserts during reset",
            "Check that o_done asserts after reset is released",
        ],
        functional_requirements=user_task_spec.refined_requirements,
        ports=_derive_ports_from_task_spec(task, user_task_spec),
        clock_and_reset=[
            ClockResetDef(
                clock_name="i_clk",
                reset_name="i_rst_n",
                reset_type=ResetType.ASYNC_LOW,
            )
        ],
        nodes=_derive_nodes(task, verify_rpt),
        edges=_derive_edges(),
    )


def _emit_verilog_from_spec(spec_reg: SpecReg) -> str:
    """
    基于当前 SpecReg 输出 Verilog RTL。

    当前实现：
    - 针对最小可运行模板输出一个简单时序模块
    - 后续可替换为模板引擎 / LLM / AST 生成器

    这里仍然坚持一个原则：
    - 代码生成应以 SpecReg 为唯一契约依据，而不是直接回看原始 prompt
    """
    top_module = spec_reg.top_module
    requirements_text = "\n".join(spec_reg.functional_requirements)

    if spec_reg.iteration == 0 and "AGVS4RTL_INJECT_FAIL_SEMANTIC_ONCE" in requirements_text:
        return (
            f"module {top_module}(\n"
            "    input wire i_clk,\n"
            "    input wire i_rst_n\n"
            ");\n"
            "\n"
            "always @(posedge i_clk or negedge i_rst_n) begin\n"
            "    if (!i_rst_n)\n"
            "        o_done <= 1'b0;\n"
            "    else\n"
            "        o_done <= 1'b1;\n"
            "end\n"
            "\n"
            "endmodule\n"
        )

    if spec_reg.iteration == 0 and "AGVS4RTL_INJECT_FAIL_COMPILE_ONCE" in requirements_text:
        return (
            f"module {top_module}(\n"
            "    input wire i_clk,\n"
            "    input wire i_rst_n,\n"
            "    output reg o_done\n"
            ");\n"
            "\n"
            "always @(posedge i_clk or negedge i_rst_n) begin\n"
            "    if (!i_rst_n) begin\n"
            "        o_done <= 1'b0;\n"
            "    else\n"
            "        o_done <= 1'b1;\n"
            "end\n"
            "\n"
            "endmodule\n"
        )

    return (
        f"module {top_module}(\n"
        "    input wire i_clk,\n"
        "    input wire i_rst_n,\n"
        "    output reg o_done\n"
        ");\n"
        "\n"
        "always @(posedge i_clk or negedge i_rst_n) begin\n"
        "    if (!i_rst_n)\n"
        "        o_done <= 1'b0;\n"
        "    else\n"
        "        o_done <= 1'b1;\n"
        "end\n"
        "\n"
        "endmodule\n"
    )


def init_context_node(state: GenWorkflowState) -> Dict[str, Any]:
    """
    节点 1：上下文初始化。

    职责：
    1. 读取 UserTaskSpec。
    2. 若 iteration > 0，尝试读取上一轮 SpecReg。
    3. 若 iteration > 0，尝试读取上一轮 VerifyRpt。
    4. 构建统一 messages，上下文供后续 Architect/Coder 复用。
    """
    task = state["task"]
    shared_task_dir = Path(task.shared_task_dir)

    user_task_spec = _load_user_task_spec(task)

    previous_spec_reg = None
    verify_rpt = None

    if task.is_retry_iteration():
        previous_iteration = task.iteration - 1
        previous_spec_reg = _load_previous_spec_reg(shared_task_dir, previous_iteration)
        verify_rpt = _load_previous_verify_rpt(shared_task_dir, previous_iteration)

    messages = _build_system_messages(
        task=task,
        user_task_spec=user_task_spec,
        previous_spec_reg=previous_spec_reg,
        verify_rpt=verify_rpt,
    )

    return {
        "iteration": task.iteration,
        "messages": messages,
        "user_task_spec": user_task_spec,
        "verify_rpt": verify_rpt,
        "previous_spec_reg": previous_spec_reg,
    }


def architect_node(state: GenWorkflowState) -> Dict[str, Any]:
    """
    节点 2：架构师节点。

    当前职责：
    1. 基于 UserTaskSpec 生成结构化 SpecReg。
    2. 若是重试轮次，则参考 VerifyRpt 调整本轮描述与上下文语义。
    3. 输出严格满足当前 models.py 约束的 SpecReg。

    后续 LLM 接入点：
    - 可在本节点中用 state["messages"] 驱动模型生成 SpecReg JSON，
      再用 SpecReg.model_validate(...) 做强约束校验。
    """
    task = state["task"]
    user_task_spec = state.get("user_task_spec")
    verify_rpt = state.get("verify_rpt")

    if user_task_spec is None:
        raise ValueError("user_task_spec is missing")

    spec_reg = _build_dummy_spec_reg(
        task=task,
        user_task_spec=user_task_spec,
        verify_rpt=verify_rpt,
    )

    return {"spec_reg": spec_reg}


def coder_node(state: GenWorkflowState) -> Dict[str, Any]:
    """
    节点 3：程序员节点。

    当前职责：
    1. 仅依据 SpecReg 生成 RTL 代码。
    2. 不直接依赖原始 prompt，避免设计事实漂移。
    3. 输出最终 Verilog 字符串。

    后续 LLM 接入点：
    - 可在本节点中将 SpecReg 序列化为上下文提示，让模型生成 RTL；
    - 再对生成结果做静态格式化与必要的语法保护。
    """
    spec_reg = state.get("spec_reg")
    if spec_reg is None:
        raise ValueError("spec_reg is missing")

    rtl_code = _emit_verilog_from_spec(spec_reg)
    return {"rtl_code": rtl_code}


def finalize_node(state: GenWorkflowState) -> Dict[str, Any]:
    """
    节点 4：落盘与输出节点。

    职责：
    1. 将 SpecReg 落盘到 shared_workspace/TASK_ID/specs。
    2. 将 RTL 落盘到 shared_workspace/TASK_ID/rtl。
    3. 组装并返回 GenNodeOutput。

    文件命名规则：
    - SpecReg: specs/SpecReg_iter{iteration}.json
    - RTL: rtl/{top_module}.v
    """
    task = state["task"]
    spec_reg = state.get("spec_reg")
    rtl_code = state.get("rtl_code")

    if spec_reg is None:
        raise ValueError("spec_reg is missing at finalize stage")
    if rtl_code is None:
        raise ValueError("rtl_code is missing at finalize stage")

    requirements_text = "\n".join(spec_reg.functional_requirements)
    shared_task_dir = Path(task.shared_task_dir)
    specs_dir = shared_task_dir / "specs"
    rtl_dir = shared_task_dir / "rtl"

    specs_dir.mkdir(parents=True, exist_ok=True)
    rtl_dir.mkdir(parents=True, exist_ok=True)

    spec_file_path = specs_dir / f"SpecReg_iter{task.iteration}.json"
    spec_file_path.write_text(spec_reg.model_dump_json(indent=2), encoding="utf-8")

    rtl_path = rtl_dir / f"{task.top_module}.v"
    rtl_path.write_text(rtl_code, encoding="utf-8")
    if task.iteration == 0 and "AGVS4RTL_INJECT_INFRA_MISSING_RTL_ONCE" in requirements_text:
        rtl_path.unlink()

    verify_rpt = state.get("verify_rpt")
    summary = f"Generated SpecReg and RTL for {task.top_module} at iteration {task.iteration}"
    if verify_rpt is not None:
        summary += f" after previous verification verdict {verify_rpt.verdict}"

    gen_output = GenNodeOutput(
        spec_file_path=str(spec_file_path),
        rtl_path=str(rtl_path),
        summary=summary,
    )

    return {"gen_output": gen_output}


def build_gen_workflow_graph():
    """
    构建 Generator 内部状态机。

    当前执行路径：
    START
      -> init_context
      -> architect
      -> coder
      -> finalize
      -> END

    后续可扩展方向：
    - architect/coder 之间加入“是否还存在未细化 instance 节点”的条件循环
    - 增加 static lint / 格式化节点
    - 增加中间产物自检节点
    """
    graph = StateGraph(GenWorkflowState)

    graph.add_node("init_context", init_context_node)
    graph.add_node("architect", architect_node)
    graph.add_node("coder", coder_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "init_context")
    graph.add_edge("init_context", "architect")
    graph.add_edge("architect", "coder")
    graph.add_edge("coder", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


def run_gen_workflow(payload: WorkTaskPayload) -> GenNodeOutput:
    """
    Generator 工作流统一入口。

    输入：
    - Parser 下发的 WorkTaskPayload

    输出：
    - GenNodeOutput（仅包含路径与摘要，不直接返回大文本代码）
    """
    app = build_gen_workflow_graph()

    initial_state: GenWorkflowState = {
        "task": payload,
        "iteration": payload.iteration,
        "messages": [],
        "user_task_spec": None,
        "verify_rpt": None,
        "previous_spec_reg": None,
        "spec_reg": None,
        "rtl_code": None,
        "gen_output": None,
    }

    final_state = app.invoke(initial_state)

    gen_output = final_state.get("gen_output")
    if gen_output is None:
        raise RuntimeError("generation workflow failed to produce GenNodeOutput")

    return gen_output