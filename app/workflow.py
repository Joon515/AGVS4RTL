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

from app.generate_agent import codegen_framework_node
from app.manage_agent import (
    AGVSState,
    architecture_design_node,
    manager_orchestration_node,
    ppa_estimation_node,
    verify_consistency_node,
)
from app.pre_agent.parser_agent import parse_requirement_node


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
    """Create workflow graph that extends to manager orchestration.

    Workflow:
        START → Parser → Architect → PPA Estimator → Manager → END
    """
    workflow = StateGraph(AGVSState)

    workflow.add_node("parser", parse_requirement_node)
    workflow.add_node("architect", architecture_design_node)
    workflow.add_node("ppa_estimator", ppa_estimation_node)
    workflow.add_node("manager", manager_orchestration_node)

    workflow.set_entry_point("parser")
    workflow.add_edge("parser", "architect")
    workflow.add_edge("architect", "ppa_estimator")
    workflow.add_edge("ppa_estimator", "manager")
    workflow.add_edge("manager", END)

    return workflow.compile()


def create_full_codegen_workflow() -> StateGraph:
    """Create full workflow graph with consistency verification.

    Workflow:
        START → Parser(NLP) → Architect → Codegen → Verify → END
    """
    workflow = StateGraph(AGVSState)

    workflow.add_node("parser", parse_requirement_node)
    workflow.add_node("architect", architecture_design_node)
    workflow.add_node("codegen", codegen_framework_node)
    workflow.add_node("verify", verify_consistency_node)

    workflow.set_entry_point("parser")
    workflow.add_edge("parser", "architect")
    workflow.add_edge("architect", "codegen")
    workflow.add_edge("codegen", "verify")
    workflow.add_edge("verify", END)

    return workflow.compile()


def run_full_codegen_workflow(
    natural_language: str,
    language: str = "zh",
    source: str = "tui",
) -> Dict[str, Any]:
    """Execute full workflow: NLP -> Architect -> Codegen -> Verify."""
    workflow = create_full_codegen_workflow()

    initial_state = {
        "natural_language": natural_language,
        "language": language,
        "source": source,
    }

    return workflow.invoke(initial_state)
