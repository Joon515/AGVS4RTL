from __future__ import annotations

import operator
import json
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from src.common.models import (
    ClockResetDef,
    GenNodeOutput,
    NodeType,
    PortDef,
    PortDirection,
    ProtocolGroup,
    ResetType,
    RtlEdge,
    RtlNode,
    SpecReg,
    UserTaskSpec,
    VerifyRpt,
    WorkTaskPayload,
)


class GenWorkflowState(TypedDict):
    """Generator 工作流的内部状态机，在图节点间传递。"""
    task: WorkTaskPayload
    iteration: int
    # 存放多轮对话的上下文 (LangChain Messages)
    messages: Annotated[List[Any], operator.add]
    # 从文件加载的原始用户任务规约
    user_task_spec: Optional[UserTaskSpec]
    # (重试时) 从文件加载的上一轮验证报告
    verify_rpt: Optional[VerifyRpt]
    # 逐步完善的图结构规约
    spec_reg: Optional[SpecReg]
    # 生成的 Verilog 源码
    rtl_code: Optional[str]
    # 最终输出载荷
    gen_output: Optional[GenNodeOutput]


def init_context_node(state: GenWorkflowState) -> Dict[str, Any]:
    """
    节点 1：上下文初始化。
    职责：读取 UserTaskSpec，并在重试时加载上一轮的 SpecReg 和 VerifyRpt，
    为“架构师”节点准备好初始的对话上下文。
    """
    task = state["task"]
    shared_task_dir = Path(task.shared_task_dir)
    messages = []

    # 1. 读取由 Parser 生成的 UserTaskSpec.json
    user_task_spec_path = Path(task.spec_file_path)
    if not user_task_spec_path.exists():
        raise FileNotFoundError(f"UserTaskSpec not found at {user_task_spec_path}")

    user_task_spec = UserTaskSpec.model_validate_json(user_task_spec_path.read_text(encoding="utf-8"))

    # 2. 构建初始的 LLM 对话上下文 (System Prompt)
    # TODO: 此处应替换为更精细的 System Prompt 模板
    system_prompt = f"""You are an expert RTL design architect. Your goal is to generate a detailed hardware module specification (SpecReg) based on the user's requirements.
The top module is `{task.top_module}`.
The user's refined requirements are: {user_task_spec.refined_requirements}
"""
    messages.append({"role": "system", "content": system_prompt})

    # 3. 如果是重试迭代 (iteration > 0)，加载上一轮的产物和报错信息
    verify_rpt = None
    if task.iteration > 0:
        # 3.1 加载上一轮的 SpecReg
        prev_spec_path = shared_task_dir / "specs" / f"SpecReg_iter{task.iteration - 1}.json"
        if prev_spec_path.exists():
            prev_spec_reg_json = prev_spec_path.read_text(encoding="utf-8")
            messages.append({"role": "system", "content": f"Here is the SpecReg from the previous attempt:\n{prev_spec_reg_json}"})

        # 3.2 加载上一轮的 VerifyRpt
        # 假设 Parser 在发起重试前，已将 VerifyRpt 保存至此路径
        verify_rpt_path = shared_task_dir / "sim" / f"VerifyRpt_iter{task.iteration - 1}.json"
        if verify_rpt_path.exists():
            verify_rpt = VerifyRpt.model_validate_json(verify_rpt_path.read_text(encoding="utf-8"))
            error_details = verify_rpt.error_details.model_dump_json(indent=2)
            # 将错误信息注入上下文，引导模型进行修复
            error_prompt = f"""The previous attempt failed verification. Here is the error report:
{error_details}
The suggested fix was: {verify_rpt.error_details.suggested_fix}
Please analyze the errors and the previous SpecReg, then generate a corrected SpecReg.
"""
            messages.append({"role": "user", "content": error_prompt})
        else:
            # 如果找不到验证报告，也需要告知模型
            messages.append({"role": "user", "content": "The previous attempt failed, but the detailed error report is missing. Please re-evaluate the requirements and try to generate a new design."})

    return {
        "iteration": task.iteration,
        "messages": messages,
        "user_task_spec": user_task_spec,
        "verify_rpt": verify_rpt,
    }


def architect_node(state: GenWorkflowState) -> Dict[str, Any]:
    """
    节点 2：架构师节点。
    职责：作为“架构师”，基于对话上下文（messages）进行推理，逐步展开模块图结构，
    细化 Nodes 和 Edges，最终生成或更新 SpecReg 规约。
    """
    task = state["task"]
    
    # TODO: 接入大模型，基于 state["messages"] 进行图结构推理。
    # 此处暂时用硬编码模拟一次图节点的生成，以确保测试链路通畅。
    dummy_spec_reg = SpecReg(
        task_id=task.task_id,
        iteration=task.iteration,
        intent=task.intent,
        top_module=task.top_module,
        module_description=f"Automated SpecReg for {task.top_module}",
        ports=[
            PortDef(name="i_clk", direction=PortDirection.INPUT, width="1", clock_domain="i_clk"),
            PortDef(name="i_rst_n", direction=PortDirection.INPUT, width="1", clock_domain="i_clk"),
            PortDef(name="o_done", direction=PortDirection.OUTPUT, width="1", clock_domain="i_clk"),
        ],
        clock_and_reset=[
            ClockResetDef(clock_name="i_clk", reset_name="i_rst_n", reset_type=ResetType.ASYNC_LOW),
        ],
        nodes=[
            RtlNode(
                node_id="seq_done_logic",
                node_type=NodeType.SEQUENTIAL,
                description="基础时序逻辑块：在复位时将 o_done 置 0，否则置 1",
                is_leaf=True,
            )
        ],
        edges=[
            RtlEdge(source="seq_done_logic.q", target="TOP.o_done", signal_name="o_done"),
            RtlEdge(source="TOP.i_clk", target="seq_done_logic.clk", signal_name="i_clk")
        ]
    )
    
    return {"spec_reg": dummy_spec_reg}


def coder_node(state: GenWorkflowState) -> Dict[str, Any]:
    """
    节点 3：程序员节点。
    职责：作为“程序员”，严格依据 `spec_reg` 里的叶子节点 (is_leaf=True)
    和连线关系 (edges) 将其翻译为功能等价的 Verilog HDL 代码。
    """
    task = state["task"]
    
    # TODO: 接入大模型或模板引擎 (如 Jinja2) 将 SpecReg 转译为代码。
    # 此处暂时用硬编码代替，以确保测试链路通畅。
    rtl_code = (
        f"module {task.top_module}(\n"
        "    input wire i_clk,\n"
        "    input wire i_rst_n,\n"
        "    output reg o_done\n"
        ");\n"
        "always @(posedge i_clk or negedge i_rst_n) begin\n"
        "    if (!i_rst_n) o_done <= 1'b0;\n"
        "    else o_done <= 1'b1;\n"
        "end\n"
        "endmodule\n"
    )
    
    return {"rtl_code": rtl_code}


def finalize_node(state: GenWorkflowState) -> Dict[str, Any]:
    """
    节点 4：归档与输出节点。
    职责：将最终生成的 SpecReg 和 RTL 代码落盘到共享工作区，并组装 GenNodeOutput。
    """
    task = state["task"]
    spec_reg = state["spec_reg"]
    rtl_code = state["rtl_code"]

    shared_task_dir = Path(task.shared_task_dir)
    specs_dir = shared_task_dir / "specs"
    rtl_dir = shared_task_dir / "rtl"
    specs_dir.mkdir(parents=True, exist_ok=True)
    rtl_dir.mkdir(parents=True, exist_ok=True)

    # 落盘 SpecReg
    spec_file_path = specs_dir / f"SpecReg_iter{task.iteration}.json"
    spec_file_path.write_text(spec_reg.model_dump_json(indent=2), encoding="utf-8")

    # 落盘 RTL 代码
    rtl_path = rtl_dir / f"{task.top_module}.v"
    rtl_path.write_text(rtl_code, encoding="utf-8")

    gen_output = GenNodeOutput(
        spec_file_path=str(spec_file_path),
        rtl_path=str(rtl_path),
        summary=f"Generated AST Spec and RTL for {task.top_module} at iteration {task.iteration}"
    )
    return {"gen_output": gen_output}


def build_gen_workflow_graph():
    """构建并装配 Generator 的内部工作流图。"""
    graph = StateGraph(GenWorkflowState)
    graph.add_node("init_context", init_context_node)
    graph.add_node("architect", architect_node)
    graph.add_node("coder", coder_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "init_context")
    graph.add_edge("init_context", "architect")
    
    # TODO: (进阶功能) 后期可在 architect 和 coder 之间加入条件路由，
    # 判断是否所有 instance 节点都已细化为 leaf 节点。若未细化，则循环调用 architect 节点进行“渐进式细化”。
    graph.add_edge("architect", "coder")
    
    graph.add_edge("coder", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


def run_gen_workflow(payload: WorkTaskPayload) -> GenNodeOutput:
    """执行 Generator 工作流的入口函数。"""
    app = build_gen_workflow_graph()
    initial_state: GenWorkflowState = {
        "task": payload,
        "iteration": payload.iteration,
        "messages": [],
        "user_task_spec": None,
        "verify_rpt": None,
        "spec_reg": None,
        "rtl_code": None,
        "gen_output": None,
    }
    final_state = app.invoke(initial_state)
    
    gen_output = final_state.get("gen_output")
    if not gen_output:
        raise RuntimeError("Generation workflow failed to produce GenNodeOutput")
    return gen_output