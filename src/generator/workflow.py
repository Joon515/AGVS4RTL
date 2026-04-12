from __future__ import annotations

import operator
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
    WorkTaskPayload,
)


class GenWorkflowState(TypedDict):
    task: WorkTaskPayload
    iteration: int
    # 存放多轮对话的上下文 (LangChain Messages)
    messages: Annotated[List[Any], operator.add]
    # 逐步完善的图结构规约
    spec_reg: Optional[SpecReg]
    # 生成的 Verilog 源码
    rtl_code: Optional[str]
    # 最终输出载荷
    gen_output: Optional[GenNodeOutput]


def init_context_node(state: GenWorkflowState) -> Dict[str, Any]:
    """
    节点 1：上下文初始化。
    读取 UserTaskSpec、历史 SpecReg (若有)、验证报告 VerifyRpt (若有)。
    """
    task = state["task"]
    iteration = task.iteration
    
    # TODO: 实际应从 task.shared_task_dir 读取 UserTaskSpec.json
    # 若 iteration > 0，还要读取上一轮的验证报错日志和旧版 SpecReg
    
    return {"iteration": iteration}


def architect_node(state: GenWorkflowState) -> Dict[str, Any]:
    """
    节点 2：架构师节点。
    负责逐步展开模块图结构，细化 Nodes 和 Edges，最终生成或更新 SpecReg。
    """
    task = state["task"]
    
    # TODO: 接入大模型，进行图结构细化的推理。这里暂时用硬编码模拟一次图节点的生成。
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
    根据 spec_reg 里的叶子节点 (is_leaf=True) 和连线关系翻译为 Verilog。
    """
    task = state["task"]
    
    # TODO: 接入大模型或模板引擎将 SpecReg 转译为代码。这里暂用硬编码代替。
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
    将结果落盘到 SharedWorkspace 并组装 GenNodeOutput。
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
    graph = StateGraph(GenWorkflowState)
    graph.add_node("init_context", init_context_node)
    graph.add_node("architect", architect_node)
    graph.add_node("coder", coder_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "init_context")
    graph.add_edge("init_context", "architect")
    
    # TODO: 后期可以在 architect 和 coder 之间加入 conditional_edge
    # 判断是否所有 instance 节点都已细化为 leaf 节点。若未细化，则循环细化。
    graph.add_edge("architect", "coder")
    
    graph.add_edge("coder", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


def run_gen_workflow(payload: WorkTaskPayload) -> GenNodeOutput:
    app = build_gen_workflow_graph()
    initial_state: GenWorkflowState = {
        "task": payload,
        "iteration": payload.iteration,
        "messages": [],
        "spec_reg": None,
        "rtl_code": None,
        "gen_output": None,
    }
    final_state = app.invoke(initial_state)
    
    gen_output = final_state.get("gen_output")
    if not gen_output:
        raise RuntimeError("Generation workflow failed to produce GenNodeOutput")
    return gen_output