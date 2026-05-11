from __future__ import annotations

import logging
import operator
import json
import re
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph

from src.common.models import (
    AGVS4RTL_INJECT_FAIL_COMPILE,
    AGVS4RTL_INJECT_FAIL_PORT_DIRECTION,
    AGVS4RTL_INJECT_FAIL_PORT_WIDTH,
    AGVS4RTL_INJECT_FAIL_SEMANTIC,
    AGVS4RTL_INJECT_INFRA_MISSING_RTL,
    ArtifactSourceStage,
    ClockResetDef,
    EndpointRef,
    GenNodeOutput,
    LlmRuntimeConfig,
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

from src.common.llm_utils import (
    _chat_completions_url,
    _extract_json_object,
    _call_openai_compatible_chat,
)

logger = logging.getLogger(__name__)


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
    llm_config: Optional[LlmRuntimeConfig]
    llm_transcripts: Annotated[List[Dict[str, Any]], operator.add]


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

    try:
        return SpecReg.model_validate_json(prev_spec_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Corrupt SpecReg at %s: %s", prev_spec_path, exc)
        return None


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

    try:
        return VerifyRpt.model_validate_json(verify_rpt_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Corrupt VerifyRpt at %s: %s", verify_rpt_path, exc)
        return None


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

    json_template = """{
  "ports": [{"name": "i_data", "direction": "input", "net_type": "wire", "width": "32", "description": ""}],
  "parameters": [{"name": "XLEN", "default_value": "32", "description": "data width"}],
  "clock_and_reset": [{"clock_name": "clk", "reset_name": "rst_n", "reset_type": "ASYNC_LOW"}],
  "protocols": [{"protocol_type": "AXI4", "role": "master", "port_mapping": {"data": "i_data"}, "description": ""}],
  "nodes": [{"node_id": "u_alu", "node_type": "INSTANCE", "module_name": "alu", "source_file": "alu.v", "description": "", "is_leaf": false}],
  "edges": [{"source": {"node_id": "TOP", "port_name": "i_clk"}, "target": {"node_id": "u_alu", "port_name": "clk"}, "signal_name": "clk", "width": "1", "description": ""}]
}"""

    system_prompt = f"""You are an expert RTL architect and coding assistant.
Your task is to generate a correct SpecReg and Verilog RTL implementation.

Top module: {task.top_module}
Intent: {task.intent}
Iteration: {task.iteration}

Refined requirements:
{user_task_spec.refined_requirements}

Design rules:
{user_task_spec.design_rules}

CRITICAL — You MUST output a JSON object that matches this EXACT structure.
Replace placeholder values with actual design specifics. Do NOT add or remove fields.

```json
{json_template}
```

RULES:
- All enum values are UPPERCASE: INSTANCE, COMBINATIONAL, SEQUENTIAL, INPUT, OUTPUT, INOUT, ASYNC_LOW, ASYNC_HIGH, SYNC_LOW, SYNC_HIGH
- ports[].direction: "input" | "output" | "inout"
- nodes[].node_type: "INSTANCE" | "COMBINATIONAL" | "SEQUENTIAL"
- clock_and_reset[].reset_type: "ASYNC_LOW" | "ASYNC_HIGH" | "SYNC_LOW" | "SYNC_HIGH"
- parameters are objects with name/default_value/description (NOT strings)
- edges source/target are objects with node_id/port_name
- DO NOT add fields not shown above
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


def _apply_fix_from_verify_rpt(spec_reg: SpecReg, verify_rpt: VerifyRpt) -> SpecReg:
    """
    Apply minimal repair to SpecReg based on VerifyRpt error details.

    Handles 1 concrete mismatch type from PortMismatch detail field:
    1. "missing" / "unexpected" → add/remove port
    """
    port_map = {p.name: p for p in spec_reg.ports}
    updated_ports = list(spec_reg.ports)

    for mismatch in verify_rpt.error_details.mismatched_ports:
        detail = mismatch.detail or ""

        if "missing" in detail:
            if "unexpected" in detail:
                new_port = PortDef(
                    name=mismatch.actual_port or mismatch.expected_port,
                    direction=PortDirection.INPUT,
                    width="1",
                    description="Auto-added from VerifyRpt: previously unexpected port",
                )
                updated_ports.append(new_port)

    return spec_reg.model_copy(
        update={
            "ports": updated_ports,
            "refactor_label": verify_rpt.suggested_refactor_level(),
        }
    )


def _build_hierarchical_spec_reg(
    task, user_task_spec, verify_rpt,
) -> SpecReg:
    """生成层次化 SpecReg，包含 INSTANCE 节点及 source_file 映射。"""
    module_description = f"Hierarchical SpecReg for {task.top_module}"
    if verify_rpt is not None:
        module_description += f" (regenerated after {verify_rpt.verdict})"
    return SpecReg(
        task_id=task.task_id, iteration=task.iteration, intent=task.intent,
        top_module=task.top_module, source_stage=ArtifactSourceStage.ARCHITECT,
        module_description=module_description,
        verification_directives=["Check sub-module instantiation chains"],
        functional_requirements=user_task_spec.refined_requirements,
        ports=_derive_ports_from_task_spec(task, user_task_spec),
        clock_and_reset=[ClockResetDef(clock_name="i_clk", reset_name="i_rst_n", reset_type=ResetType.ASYNC_LOW)],
        nodes=[
            RtlNode(node_id="u_counter", node_type=NodeType.INSTANCE, module_name="counter",
                     source_file="counter.v", description="Simple counter sub-module", is_leaf=False),
            RtlNode(node_id="u_comparator", node_type=NodeType.INSTANCE, module_name="comparator",
                     source_file="comparator.v", description="Value comparator sub-module", is_leaf=False),
        ],
        edges=[
            RtlEdge(source=EndpointRef(node_id="TOP", port_name="i_clk"),
                     target=EndpointRef(node_id="u_counter", port_name="clk"), signal_name="clk", width="1"),
            RtlEdge(source=EndpointRef(node_id="TOP", port_name="i_rst_n"),
                     target=EndpointRef(node_id="u_counter", port_name="rst_n"), signal_name="rst_n", width="1"),
            RtlEdge(source=EndpointRef(node_id="u_counter", port_name="count"),
                     target=EndpointRef(node_id="u_comparator", port_name="value"), signal_name="count_val", width="8"),
            RtlEdge(source=EndpointRef(node_id="u_comparator", port_name="done"),
                     target=EndpointRef(node_id="TOP", port_name="o_done"), signal_name="o_done", width="1"),
        ],
    )


def _is_hierarchical_request(task, user_task_spec=None) -> bool:
    """判断是否应生成层次化设计。"""
    if "hier" in task.top_module.lower():
        return True
    if user_task_spec is not None:
        combined = " ".join(user_task_spec.refined_requirements + user_task_spec.design_rules)
        if "AGVS4RTL_INJECT_HIERARCHICAL" in combined:
            return True
    return False


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
        source_stage=ArtifactSourceStage.ARCHITECT,
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

    if spec_reg.iteration == 0 and AGVS4RTL_INJECT_FAIL_SEMANTIC in requirements_text:
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

    if spec_reg.iteration == 0 and AGVS4RTL_INJECT_FAIL_COMPILE in requirements_text:
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

    if spec_reg.iteration == 0 and AGVS4RTL_INJECT_FAIL_PORT_DIRECTION in requirements_text:
        return (
            f"module {top_module}(\n"
            "    input wire i_clk,\n"
            "    input wire i_rst_n,\n"
            "    input wire o_done\n"
            ");\n"
            "\n"
            "endmodule\n"
        )

    if spec_reg.iteration == 0 and AGVS4RTL_INJECT_FAIL_PORT_WIDTH in requirements_text:
        return (
            f"module {top_module}(\n"
            "    input wire i_clk,\n"
            "    input wire i_rst_n,\n"
            "    output reg [1:0] o_done\n"
            ");\n"
            "\n"
            "always @(posedge i_clk or negedge i_rst_n) begin\n"
            "    if (!i_rst_n)\n"
            "        o_done <= 2'b00;\n"
            "    else\n"
            "        o_done <= 2'b01;\n"
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


def _derive_submodule_ports(node: RtlNode, spec_reg: SpecReg) -> List[PortDef]:
    """
    从连接到该节点的边推导子模块端口列表。

    遍历 SpecReg 中的所有 RtlEdge，找出 source 或 target 为
    该节点的端口，并推导方向。同时附加顶层时钟/复位端口。
    """
    seen_ports: Dict[str, PortDef] = {}
    for edge in spec_reg.edges:
        if edge.source.node_id == node.node_id:
            port = PortDef(
                name=edge.source.port_name,
                direction=PortDirection.OUTPUT,
                width=edge.width,
            )
            if port.name not in seen_ports:
                seen_ports[port.name] = port
            elif seen_ports[port.name].direction == PortDirection.INPUT:
                seen_ports[port.name] = seen_ports[port.name].model_copy(
                    update={"direction": PortDirection.INOUT}
                )
        if edge.target.node_id == node.node_id:
            port = PortDef(
                name=edge.target.port_name,
                direction=PortDirection.INPUT,
                width=edge.width,
            )
            if port.name not in seen_ports:
                seen_ports[port.name] = port
            elif seen_ports[port.name].direction == PortDirection.OUTPUT:
                seen_ports[port.name] = seen_ports[port.name].model_copy(
                    update={"direction": PortDirection.INOUT}
                )
    ports = list(seen_ports.values())

    if spec_reg.has_clock_reset_definition():
        cr = spec_reg.clock_and_reset[0]
        if cr.clock_name not in seen_ports:
            ports.append(
                PortDef(
                    name=cr.clock_name,
                    direction=PortDirection.INPUT,
                    width="1",
                    is_clock=True,
                )
            )
        if cr.reset_name not in seen_ports:
            ports.append(
                PortDef(
                    name=cr.reset_name,
                    direction=PortDirection.INPUT,
                    width="1",
                    is_reset=True,
                )
            )
    return ports


def _emit_submodule_verilog(
    node: RtlNode,
    ports: List[PortDef],
    spec_reg: SpecReg,
) -> str:
    """
    根据节点定义生成最小子模块 Verilog 骨架。

    生成的模块包含端口声明、描述注释和 TODO 占位符，
    不生成实际逻辑代码。
    """
    port_lines: List[str] = []
    for p in ports:
        direction = p.direction.value
        if p.width != "1":
            port_lines.append(f"    {direction} wire [{p.width}:0] {p.name}")
        else:
            port_lines.append(f"    {direction} wire {p.name}")
    port_block = ",\n".join(port_lines)

    return (
        f"module {node.module_name}(\n"
        f"{port_block}\n"
        f");\n"
        f"\n"
        f"// {node.description}\n"
        f"// TODO: Implement {node.node_type.value} logic for {node.node_id}\n"
        f"\n"
        f"endmodule\n"
    )


def _has_injection_directive(spec_reg: SpecReg) -> bool:
    requirements_text = "\n".join(spec_reg.functional_requirements)
    return "AGVS4RTL_INJECT_" in requirements_text


def _has_injection_in_user_task_spec(user_task_spec: UserTaskSpec) -> bool:
    request_text = "\n".join(
        [
            *user_task_spec.refined_requirements,
            *user_task_spec.design_rules,
        ]
    )
    return "AGVS4RTL_INJECT_" in request_text


def _extract_verilog_code(content: str) -> str:
    fence_match = re.search(r"```(?:systemverilog|verilog|sv)?\s*(.*?)```", content, re.IGNORECASE | re.DOTALL)
    if fence_match is not None:
        content = fence_match.group(1)

    content = content.strip()
    module_index = content.find("module ")
    endmodule_index = content.rfind("endmodule")

    if module_index >= 0 and endmodule_index >= module_index:
        content = content[module_index:endmodule_index + len("endmodule")]

    if not content.startswith("module ") or "endmodule" not in content:
        raise ValueError("LLM response does not contain a complete Verilog module")

    return content.rstrip() + "\n"


def _ensure_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


# ==========================================
# Preprocessing: field alias mapping, extra-field stripping, default injection
# Defense-in-depth against LLM hallucinated field names
# ==========================================

_FIELD_ALIASES = {
    # ParameterDef
    "parameter": "default_value",
    "value": "default_value",
    # PortDef
    "port_name": "name",
    "dir": "direction",
    "io_type": "direction",
    "signal_type": "net_type",
    "data_type": "net_type",
    "bit_width": "width",
    "size": "width",
    # RtlNode — id/name->node_id and type->node_type already handled by existing normalization
    "module": "module_name",
    "source": "source_file",
    "file": "source_file",
    # ClockResetDef
    "clk": "clock_name",
    "rst": "reset_name",
    "rst_n": "reset_name",
    # Edge / EndpointRef
    "from": "source",
    "to": "target",
    "wire_name": "signal_name",
}


def _apply_aliases(obj: Any, aliases: Dict[str, Any]) -> Any:
    """Recursively rename keys in dicts/lists using the alias map."""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            target = aliases.get(k, k)
            if target is not None:  # None means strip this field entirely
                result[target] = _apply_aliases(v, aliases) if isinstance(v, (dict, list)) else v
        return result
    elif isinstance(obj, list):
        return [_apply_aliases(item, aliases) for item in obj]
    return obj


# Known field sets per sub-model (from Pydantic StrictBaseModel with extra="forbid")
_PORT_FIELDS = {"name", "direction", "net_type", "width", "clock_domain", "is_clock", "is_reset", "description"}
_NODE_FIELDS = {"node_id", "node_type", "module_name", "source_file", "description", "is_leaf"}
_CLOCK_FIELDS = {"clock_name", "reset_name", "reset_type"}
_PARAM_FIELDS = {"name", "default_value", "description"}
_PROTOCOL_FIELDS = {"protocol_type", "role", "port_mapping", "description"}
_EDGE_FIELDS = {"source", "target", "signal_name", "width", "description"}
_ENDPOINT_FIELDS = {"node_id", "port_name"}

# Top-level SpecReg fields (BaseSyncMeta + SpecReg own fields) — not stripped
_TOP_LEVEL_FIELDS = {
    "task_id", "iteration", "refactor_label", "intent", "top_module",
    "created_at", "source_stage", "module_description", "parameters",
    "ports", "clock_and_reset", "protocols", "verification_directives",
    "functional_requirements", "corner_cases", "illegal_conditions",
    "latency_notes", "nodes", "edges",
}


def _strip_extra_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Strip unknown fields from sub-objects to prevent extra_forbidden errors."""
    result = dict(payload)

    # Strip top-level extra fields
    result = {k: v for k, v in result.items() if k in _TOP_LEVEL_FIELDS}

    # Strip ports
    result["ports"] = [
        {k: v for k, v in p.items() if k in _PORT_FIELDS}
        for p in result.get("ports", []) if isinstance(p, dict)
    ]
    # Strip nodes
    result["nodes"] = [
        {k: v for k, v in n.items() if k in _NODE_FIELDS}
        for n in result.get("nodes", []) if isinstance(n, dict)
    ]
    # Strip parameters
    result["parameters"] = [
        {k: v for k, v in p.items() if k in _PARAM_FIELDS}
        for p in result.get("parameters", []) if isinstance(p, dict)
    ]
    # Strip clock_and_reset
    result["clock_and_reset"] = [
        {k: v for k, v in c.items() if k in _CLOCK_FIELDS}
        for c in result.get("clock_and_reset", []) if isinstance(c, dict)
    ]
    # Strip protocols
    result["protocols"] = [
        {k: v for k, v in p.items() if k in _PROTOCOL_FIELDS}
        for p in result.get("protocols", []) if isinstance(p, dict)
    ]
    # Strip edges (source/target are EndpointRef sub-objects)
    stripped_edges = []
    for e in result.get("edges", []):
        if not isinstance(e, dict):
            continue
        clean = {k: v for k, v in e.items() if k in _EDGE_FIELDS}
        if "source" in clean and isinstance(clean["source"], dict):
            clean["source"] = {k: v for k, v in clean["source"].items() if k in _ENDPOINT_FIELDS}
        if "target" in clean and isinstance(clean["target"], dict):
            clean["target"] = {k: v for k, v in clean["target"].items() if k in _ENDPOINT_FIELDS}
        stripped_edges.append(clean)
    result["edges"] = stripped_edges

    return result


# Smart defaults for fields the LLM frequently omits
_DEFAULTS = {
    "net_type": "wire",
    "direction": "input",
    "width": "1",
    "is_clock": False,
    "is_reset": False,
    "description": "",
    "is_leaf": False,
    "clock_domain": None,
}


def _apply_defaults(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Inject defaults for fields that are optional but frequently omitted by LLM."""
    for port in payload.get("ports", []):
        if not isinstance(port, dict):
            continue
        for key, default in _DEFAULTS.items():
            if key in _PORT_FIELDS:
                port.setdefault(key, default)

    for node in payload.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node.setdefault("description", "")
        node.setdefault("is_leaf", False)

    for param in payload.get("parameters", []):
        if not isinstance(param, dict):
            continue
        param.setdefault("description", "")

    for edge in payload.get("edges", []):
        if not isinstance(edge, dict):
            continue
        edge.setdefault("width", "1")
        edge.setdefault("description", "")

    return payload


def _normalize_architect_spec_payload(spec_payload: Dict[str, Any]) -> Dict[str, Any]:
    # === NEW: Preprocessing pipeline (defense-in-depth) ===
    # Step 1: Apply field alias mapping
    normalized = _apply_aliases(dict(spec_payload), _FIELD_ALIASES)
    # Step 2: Strip unknown fields to prevent extra_forbidden errors
    normalized = _strip_extra_fields(normalized)
    # Step 3: Inject defaults for commonly omitted fields
    normalized = _apply_defaults(normalized)
    # === END preprocessing ===

    for field_name in [
        "verification_directives",
        "functional_requirements",
        "corner_cases",
        "illegal_conditions",
        "latency_notes",
    ]:
        normalized[field_name] = _ensure_text_list(normalized.get(field_name))

    normalized.setdefault("parameters", [])
    normalized.setdefault("ports", [])
    normalized.setdefault("clock_and_reset", [])
    normalized.setdefault("protocols", [])

    # Part B: normalize parameters — LLM may output strings like "XLEN = 32" instead of objects
    raw_params = normalized.get("parameters", [])
    if raw_params and any(isinstance(p, str) for p in raw_params):
        normalized["parameters"] = [
            {"name": p.split("=")[0].strip(), "default_value": p.split("=")[1].strip(), "description": ""}
            if isinstance(p, str) and "=" in p
            else p
            for p in raw_params
        ]

    normalized_nodes = []
    for node in normalized.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        node_id = node.get("node_id") or node.get("name") or node.get("id")
        if not node_id:
            continue
        node_type = node.get("node_type") or node.get("type") or "combinational"
        _NODE_TYPE_ALIASES = {
            "module": "INSTANCE", "inst": "INSTANCE", "instance": "INSTANCE",
            "comb": "COMBINATIONAL", "combinational": "COMBINATIONAL", "combinatorial": "COMBINATIONAL",
            "seq": "SEQUENTIAL", "sequential": "SEQUENTIAL", "reg": "SEQUENTIAL", "register": "SEQUENTIAL",
        }
        # Check both node_type and type fields for aliasing (LLM may put "module" in either)
        for raw_value in filter(None, [node.get("node_type"), node.get("type")]):
            if str(raw_value).lower() in _NODE_TYPE_ALIASES:
                node_type = _NODE_TYPE_ALIASES[str(raw_value).lower()]
                break
        normalized_nodes.append(
            {
                "node_id": node_id,
                "node_type": node_type,
                "module_name": node.get("module_name"),
                "description": node.get("description", ""),
                "is_leaf": node.get("is_leaf", node_type.upper() in {"COMBINATIONAL", "SEQUENTIAL"}),
            }
        )
    normalized["nodes"] = normalized_nodes

    normalized_edges = []
    for edge in normalized.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source = edge.get("source")
        target = edge.get("target")
        if not isinstance(source, dict) or not isinstance(target, dict):
            continue
        if "node_id" not in source or "port_name" not in source:
            continue
        if "node_id" not in target or "port_name" not in target:
            continue
        signal_name = edge.get("signal_name")
        if not signal_name:
            continue
        normalized_edges.append(edge)
    normalized["edges"] = normalized_edges

    # Part A0: normalize clock_and_reset STRING arrays (LLM may output ["clk: ...", "rst: ..."])
    raw_crs = normalized.get("clock_and_reset", [])
    if raw_crs and all(isinstance(cr, str) for cr in raw_crs):
        # Pattern: "clk: global clock (posedge)" or "rst_n: active-low async reset"
        normalized_crs = []
        clocks = [cr for cr in raw_crs if "clock" in cr.lower()]
        resets = [cr for cr in raw_crs if "reset" in cr.lower()]
        for clk_str, rst_str in zip(clocks, resets):
            clk_name = clk_str.split(":")[0].strip() if ":" in clk_str else clk_str.strip()
            rst_name = rst_str.split(":")[0].strip() if ":" in rst_str else rst_str.strip()
            rst_desc = rst_str.lower()
            if "async" in rst_desc:
                reset_type = "ASYNC_LOW" if "low" in rst_desc else "ASYNC_HIGH"
            else:
                reset_type = "SYNC_LOW" if "low" in rst_desc else "SYNC_HIGH"
            normalized_crs.append({
                "clock_name": clk_name,
                "reset_name": rst_name,
                "reset_type": reset_type,
            })
        if normalized_crs:
            normalized["clock_and_reset"] = normalized_crs

    # Part A: normalize clock_and_reset — LLM may output separate {name,type,polarity,domain} objects
    raw_crs = normalized.get("clock_and_reset", [])
    if raw_crs and not all("clock_name" in cr for cr in raw_crs if isinstance(cr, dict)):
        normalized_crs = []
        clocks = [cr for cr in raw_crs if isinstance(cr, dict) and cr.get("type", "").lower() == "clock"]
        resets = [cr for cr in raw_crs if isinstance(cr, dict) and "reset" in cr.get("type", "").lower()]
        for clk, rst in zip(clocks, resets):
            reset_type = "ASYNC_LOW"
            if rst.get("polarity", "").lower() == "active_high":
                if rst.get("type", "").lower() == "async_reset":
                    reset_type = "ASYNC_HIGH"
                else:
                    reset_type = "SYNC_HIGH"
            elif rst.get("polarity", "").lower() == "active_low":
                if rst.get("type", "").lower() == "async_reset":
                    reset_type = "ASYNC_LOW"
                else:
                    reset_type = "SYNC_LOW"
            normalized_crs.append({
                "clock_name": clk.get("name", "clk"),
                "reset_name": rst.get("name", "rst_n"),
                "reset_type": reset_type,
            })
        if normalized_crs:
            normalized["clock_and_reset"] = normalized_crs

    # Part: normalize protocols — LLM may output strings like "AXI4: Master: ..."
    raw_protocols = normalized.get("protocols", [])
    if raw_protocols and all(isinstance(p, str) for p in raw_protocols):
        normalized["protocols"] = [
            {
                "protocol_type": p.split(":")[0].strip() if ":" in p else p.strip(),
                "role": p.split(":")[1].strip() if p.count(":") >= 2 else "generic",
                "port_mapping": {"default": "default_port"},
                "description": p.split(":", 2)[2].strip() if p.count(":") >= 2 else p,
            }
            for p in raw_protocols
        ]

    return normalized


def _emit_verilog_with_llm(
    spec_reg: SpecReg,
    user_task_spec: UserTaskSpec,
    verify_rpt: Optional[VerifyRpt],
    llm_config: LlmRuntimeConfig,
) -> tuple[str, Dict[str, Any]]:
    retry_context = ""
    if verify_rpt is not None:
        retry_context = "\nPrevious verification report:\n" + verify_rpt.model_dump_json(indent=2)

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert Verilog RTL engineer. Generate synthesizable Verilog-2001 only. "
                "Return exactly one complete Verilog module and no explanation."
            ),
        },
        {
            "role": "user",
            "content": (
                "Generate RTL that strictly implements this SpecReg contract. "
                "Do not change the module name, port names, port directions, or widths. "
                "Use active-low asynchronous reset when reset_type is async_low.\n\n"
                f"UserTaskSpec:\n{user_task_spec.model_dump_json(indent=2)}\n\n"
                f"SpecReg:\n{spec_reg.model_dump_json(indent=2)}"
                f"{retry_context}"
            ),
        },
    ]

    content, transcript = _call_openai_compatible_chat(llm_config, messages)
    transcript.update(
        {
            "stage": "coder",
            "profile": llm_config.profile,
            "extracted_rtl": _extract_verilog_code(content),
        }
    )
    return transcript["extracted_rtl"], transcript


def _build_spec_reg_with_llm(
    task: WorkTaskPayload,
    user_task_spec: UserTaskSpec,
    previous_spec_reg: Optional[SpecReg],
    verify_rpt: Optional[VerifyRpt],
    llm_config: LlmRuntimeConfig,
) -> tuple[SpecReg, Dict[str, Any]]:
    previous_context = ""
    if previous_spec_reg is not None:
        previous_context += "\nPrevious SpecReg:\n" + previous_spec_reg.model_dump_json(indent=2)
    if verify_rpt is not None:
        previous_context += "\nPrevious VerifyRpt:\n" + verify_rpt.model_dump_json(indent=2)

    messages = [
        {
            "role": "system",
            "content": (
                "You are the Architect node in an RTL generation workflow. "
                "Return JSON only for a complete SpecReg object. "
                "The JSON must match these top-level fields: task_id, iteration, refactor_label, "
                "intent, top_module, source_stage, module_description, parameters, ports, "
                "clock_and_reset, protocols, verification_directives, functional_requirements, "
                "corner_cases, illegal_conditions, latency_notes, nodes, edges. "
                "Use source_stage=architect. For combinational designs, clock_and_reset can be an empty list. "
                "Use width as a decimal bit count string such as '1', '3', or '8'. "
                "Use port directions input, output, or inout, and net types wire, reg, or logic. "
                "verification_directives, functional_requirements, corner_cases, illegal_conditions, "
                "and latency_notes must be arrays of strings. "
                "nodes must use node_id, node_type, module_name, description, and is_leaf. "
                "For flat combinational designs, use nodes=[] and edges=[]. "
                "Only include edges when source and target are EndpointRef objects with node_id and port_name."
            ),
        },
        {
            "role": "user",
            "content": (
                "Generate the authoritative SpecReg contract for this task. "
                "The Coder will be required to implement this SpecReg exactly, so include the real top-level ports "
                "and functional intent from UserTaskSpec. Do not invent placeholder clock/reset/done ports unless "
                "the user requirements explicitly ask for them.\n\n"
                f"Task metadata:\n{task.model_dump_json(indent=2)}\n\n"
                f"UserTaskSpec:\n{user_task_spec.model_dump_json(indent=2)}"
                f"{previous_context}"
            ),
        },
    ]

    content, transcript = _call_openai_compatible_chat(llm_config, messages)
    spec_payload = _normalize_architect_spec_payload(_extract_json_object(content))
    spec_payload.update(
        {
            "task_id": task.task_id,
            "iteration": task.iteration,
            "intent": task.intent.value,
            "top_module": task.top_module,
            "source_stage": ArtifactSourceStage.ARCHITECT.value,
        }
    )
    if not spec_payload.get("functional_requirements"):
        spec_payload["functional_requirements"] = user_task_spec.refined_requirements

    spec_reg = SpecReg.model_validate(spec_payload)
    transcript.update(
        {
            "stage": "architect",
            "profile": llm_config.profile,
            "parsed_spec_reg": spec_reg.model_dump(mode="json"),
        }
    )
    return spec_reg, transcript


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
    previous_spec_reg = state.get("previous_spec_reg")
    llm_config = state.get("llm_config")

    if user_task_spec is None:
        raise ValueError("user_task_spec is missing")

    if llm_config is not None and llm_config.enabled and not _has_injection_in_user_task_spec(user_task_spec):
        try:
            spec_reg, llm_transcript = _build_spec_reg_with_llm(
                task=task,
                user_task_spec=user_task_spec,
                previous_spec_reg=previous_spec_reg,
                verify_rpt=verify_rpt,
                llm_config=llm_config,
            )
            return {"spec_reg": spec_reg, "llm_transcripts": [llm_transcript]}
        except Exception as exc:  # noqa: BLE001
            fallback_spec_reg = (
                _build_hierarchical_spec_reg(task=task, user_task_spec=user_task_spec, verify_rpt=verify_rpt)
                if _is_hierarchical_request(task, user_task_spec)
                else _build_dummy_spec_reg(task=task,
                user_task_spec=user_task_spec,
                verify_rpt=verify_rpt,
            ))
            # Apply repair from VerifyRpt if available
            if verify_rpt is not None and verify_rpt.error_details.mismatched_ports:
                fallback_spec_reg = _apply_fix_from_verify_rpt(fallback_spec_reg, verify_rpt)
            return {
                "spec_reg": fallback_spec_reg,
                "llm_transcripts": [
                    {
                        "stage": "architect",
                        "profile": llm_config.profile,
                        "error": str(exc),
                        "fallback": "dummy_spec_reg",
                    }
                ],
            }

    if not _has_injection_in_user_task_spec(user_task_spec):
        logger.warning("LLM unavailable, falling back to dummy SpecReg")
        spec_reg = _build_dummy_spec_reg(task=task, user_task_spec=user_task_spec, verify_rpt=verify_rpt)
        if verify_rpt is not None and verify_rpt.error_details.mismatched_ports:
            spec_reg = _apply_fix_from_verify_rpt(spec_reg, verify_rpt)
        return {
            "spec_reg": spec_reg,
            "llm_transcripts": [{"fallback": "llm_unavailable"}],
        }

    spec_reg = (
        _build_hierarchical_spec_reg(task=task, user_task_spec=user_task_spec, verify_rpt=verify_rpt)
        if _is_hierarchical_request(task, user_task_spec)
        else _build_dummy_spec_reg(task=task,
        user_task_spec=user_task_spec,
        verify_rpt=verify_rpt,
    ))

    # Apply repair from VerifyRpt if available
    if verify_rpt is not None and verify_rpt.error_details.mismatched_ports:
        spec_reg = _apply_fix_from_verify_rpt(spec_reg, verify_rpt)

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
    user_task_spec = state.get("user_task_spec")
    verify_rpt = state.get("verify_rpt")
    llm_config = state.get("llm_config")
    if spec_reg is None:
        raise ValueError("spec_reg is missing")
    if user_task_spec is None:
        raise ValueError("user_task_spec is missing")

    if llm_config is not None and llm_config.enabled and not _has_injection_directive(spec_reg):
        rtl_code, llm_transcript = _emit_verilog_with_llm(
            spec_reg=spec_reg,
            user_task_spec=user_task_spec,
            verify_rpt=verify_rpt,
            llm_config=llm_config,
        )
        return {"rtl_code": rtl_code, "llm_transcripts": [llm_transcript]}

    if not _has_injection_directive(spec_reg):
        logger.warning("LLM unavailable, falling back to template RTL")
        rtl_code = _emit_verilog_from_spec(spec_reg)
        return {"rtl_code": rtl_code, "llm_transcripts": [{"fallback": "llm_unavailable"}]}

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
    llm_transcripts = state.get("llm_transcripts", [])

    if spec_reg is None:
        raise ValueError("spec_reg is missing at finalize stage")
    if rtl_code is None:
        raise ValueError("rtl_code is missing at finalize stage")

    requirements_text = "\n".join(spec_reg.functional_requirements)
    shared_task_dir = Path(task.shared_task_dir)
    specs_dir = shared_task_dir / "specs"
    rtl_dir = shared_task_dir / "rtl"
    llm_dir = shared_task_dir / "llm"

    specs_dir.mkdir(parents=True, exist_ok=True)
    rtl_dir.mkdir(parents=True, exist_ok=True)

    spec_file_path = specs_dir / f"SpecReg_iter{task.iteration}.json"
    spec_file_path.write_text(spec_reg.model_dump_json(indent=2), encoding="utf-8")

    rtl_path = rtl_dir / f"{task.top_module}.v"
    rtl_path.write_text(rtl_code, encoding="utf-8")
    if task.iteration == 0 and AGVS4RTL_INJECT_INFRA_MISSING_RTL in requirements_text:
        rtl_path.unlink()

    # 多文件输出：当 SpecReg 为层次化设计且包含 INSTANCE 节点时，
    # 为每个有 source_file 的子模块生成独立的 .v 骨架文件。
    sub_module_paths: List[str] = []
    if spec_reg.is_hierarchical_design():
        instance_nodes = spec_reg.instance_nodes()
        for node in instance_nodes:
            if node.source_file and node.module_name:
                sub_path = rtl_dir / node.source_file
                sub_path.parent.mkdir(parents=True, exist_ok=True)
                sub_ports = _derive_submodule_ports(node, spec_reg)
                sub_rtl = _emit_submodule_verilog(node, sub_ports, spec_reg)
                sub_path.write_text(sub_rtl, encoding="utf-8")
                sub_module_paths.append(str(sub_path))

    if llm_transcripts:
        llm_dir.mkdir(parents=True, exist_ok=True)
        transcripts_by_stage: Dict[str, List[Dict[str, Any]]] = {}
        for transcript in llm_transcripts:
            stage = str(transcript.get("stage", "unknown"))
            transcripts_by_stage.setdefault(stage, []).append(transcript)

        stage_file_names = {
            "architect": "ArchitectChat",
            "coder": "CoderChat",
        }
        for stage, stage_transcripts in transcripts_by_stage.items():
            trace_name = stage_file_names.get(stage, f"{stage.title()}Chat")
            llm_trace_path = llm_dir / f"{trace_name}_iter{task.iteration}.json"
            llm_trace_path.write_text(
                json.dumps(
                    {
                        "task_id": task.task_id,
                        "iteration": task.iteration,
                        "top_module": task.top_module,
                        "transcripts": stage_transcripts,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    verify_rpt = state.get("verify_rpt")
    summary = f"Generated SpecReg and RTL for {task.top_module} at iteration {task.iteration}"
    if sub_module_paths:
        summary += f"; generated {len(sub_module_paths)} sub-module files"
    if verify_rpt is not None:
        summary += f" after previous verification verdict {verify_rpt.verdict}"

    gen_output = GenNodeOutput(
        spec_file_path=str(spec_file_path),
        rtl_path=str(rtl_path),
        summary=summary,
        rtl_paths=[str(rtl_path)] + sub_module_paths if sub_module_paths else None,
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


def run_gen_workflow(payload: WorkTaskPayload, llm_config: Optional[LlmRuntimeConfig] = None) -> GenNodeOutput:
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
        "llm_config": llm_config,
        "llm_transcripts": [],
    }

    final_state = app.invoke(initial_state)

    gen_output = final_state.get("gen_output")
    if gen_output is None:
        raise RuntimeError("generation workflow failed to produce GenNodeOutput")

    return gen_output