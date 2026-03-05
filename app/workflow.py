"""LangGraph workflow for pre-Manager Agent stages.

This workflow includes:
1. Parser Agent: Natural language → Structured intent
2. Architect Agent: Intent → Module hierarchy (with RAG)
3. PPA Estimator: Architecture → Performance/Power/Area metrics

This is the first part of the complete AGVS4RTL workflow, ending at the
point where Manager Agent takes over for code generation orchestration.
"""

from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import END, StateGraph

from app.manage_agent import (
    AGVSState,
    architecture_design_node,
    create_initial_state,
    manager_orchestration_node,
    ppa_estimation_node,
)
from app.pre_agent.parser_agent import parse_requirement_node
from app.test_agent import test_generation_node


def create_pre_manager_workflow() -> StateGraph:
    """Create the pre-Manager workflow graph.
    
    Workflow:
        START → Parser → Architect → PPA Estimator → END
    
    Returns:
        Compiled StateGraph ready for execution
    """
    # Create workflow graph
    workflow = StateGraph(AGVSState)
    
    # Add nodes
    workflow.add_node("parser", parse_requirement_node)
    workflow.add_node("architect", architecture_design_node)
    workflow.add_node("ppa_estimator", ppa_estimation_node)
    
    # Define edges
    workflow.set_entry_point("parser")
    workflow.add_edge("parser", "architect")
    workflow.add_edge("architect", "ppa_estimator")
    workflow.add_edge("ppa_estimator", END)
    
    # Compile
    return workflow.compile()


def run_pre_manager_workflow(
    natural_language: str,
    language: str = "zh",
    source: str = "tui",
) -> Dict[str, Any]:
    """Execute the pre-Manager workflow.
    
    Args:
        natural_language: User's requirement text
        language: Input language ("zh" or "en")
        source: Input source ("tui" or "api")
    
    Returns:
        Final state with intent, architecture, and PPA
    """
    # Create workflow
    workflow = create_pre_manager_workflow()
    
    # Prepare initial state
    initial_state = {
        "natural_language": natural_language,
        "language": language,
        "source": source,
    }
    
    # Execute workflow
    final_state = workflow.invoke(initial_state)
    
    return final_state


def create_manager_workflow() -> StateGraph:
    """Create workflow graph including Manager Agent.

    Workflow:
        START → Parser → Architect → PPA Estimator → Manager → Test Generator → END

    Returns:
        Compiled StateGraph ready for execution
    """
    workflow = StateGraph(AGVSState)

    workflow.add_node("parser", parse_requirement_node)
    workflow.add_node("architect", architecture_design_node)
    workflow.add_node("ppa_estimator", ppa_estimation_node)
    workflow.add_node("manager", manager_orchestration_node)
    workflow.add_node("test_generator", test_generation_node)

    workflow.set_entry_point("parser")
    workflow.add_edge("parser", "architect")
    workflow.add_edge("architect", "ppa_estimator")
    workflow.add_edge("ppa_estimator", "manager")
    workflow.add_edge("manager", "test_generator")
    workflow.add_edge("test_generator", END)

    return workflow.compile()


def run_manager_workflow(
    natural_language: str,
    language: str = "zh",
    source: str = "tui",
) -> Dict[str, Any]:
    """Execute workflow through Manager and Test stages.

    Args:
        natural_language: User's requirement text
        language: Input language ("zh" or "en")
        source: Input source ("tui" or "api")

    Returns:
        Final state with manager orchestration and static test output
    """
    workflow = create_manager_workflow()
    initial_state = {
        "natural_language": natural_language,
        "language": language,
        "source": source,
    }
    return workflow.invoke(initial_state)


# Example usage
if __name__ == "__main__":
    # Example requirement
    requirement = """
    设计一个带AXI4-Lite接口的32位寄存器文件，支持4KB地址空间。
    工作频率200MHz，低功耗设计。
    """
    
    print("=" * 60)
    print("AGVS4RTL Pre-Manager Workflow Demo")
    print("=" * 60)
    print(f"\n需求: {requirement.strip()}\n")
    
    # Run workflow
    print("执行工作流...")
    result = run_pre_manager_workflow(requirement)
    
    # Display results
    print("\n" + "=" * 60)
    print("1. 解析结果 (Parser Agent)")
    print("=" * 60)
    intent = result.get("intent", {})
    print(f"摘要: {intent.get('summary', 'N/A')}")
    print(f"接口: {', '.join(intent.get('interfaces', []))}")
    print(f"时钟: {intent.get('clock', 'N/A')}")
    print(f"复位: {intent.get('reset', 'N/A')}")
    
    print("\n" + "=" * 60)
    print("2. 架构设计 (Architect Agent)")
    print("=" * 60)
    architecture = result.get("architecture", {})
    hierarchy = architecture.get("hierarchy", {})
    top = hierarchy.get("top", {})
    print(f"顶层模块: {top.get('name', 'N/A')}")
    print(f"子模块数量: {len(hierarchy.get('modules', []))}")
    if hierarchy.get("modules"):
        print("子模块列表:")
        for module in hierarchy.get("modules", []):
            print(f"  - {module.get('name', 'N/A')} ({module.get('type', 'N/A')})")
    
    print("\n" + "=" * 60)
    print("3. PPA评估 (PPA Estimator)")
    print("=" * 60)
    ppa = result.get("ppa", {})
    area = ppa.get("area", {})
    power = ppa.get("power", {})
    timing = ppa.get("timing", {})
    
    print(f"面积: {area.get('total_gates', 'N/A')} GE")
    print(f"  - 寄存器: {area.get('breakdown', {}).get('registers', 'N/A')}")
    print(f"  - 组合逻辑: {area.get('breakdown', {}).get('combinational', 'N/A')}")
    
    print(f"\n功耗: {power.get('total_mw', 'N/A')} mW")
    print(f"  - 动态功耗: {power.get('dynamic_mw', 'N/A')} mW")
    print(f"  - 静态功耗: {power.get('static_mw', 'N/A')} mW")
    
    print(f"\n时序: 最大频率 {timing.get('max_freq_mhz', 'N/A')} MHz")
    critical_path = timing.get("critical_path", {})
    print(f"  - 关键路径延迟: {critical_path.get('delay_ns', 'N/A')} ns")
    print(f"  - 时序裕量: {critical_path.get('slack_ns', 'N/A')} ns")
    
    print(f"\n可行性评级: {ppa.get('feasibility', 'N/A').upper()}")
    
    warnings = ppa.get("warnings", [])
    if warnings:
        print("\n警告信息:")
        for warning in warnings:
            severity = warning.get("severity", "info").upper()
            message = warning.get("message", "")
            print(f"  [{severity}] {message}")
    
    print("\n" + "=" * 60)
    print("工作流完成！")
    print("=" * 60)
