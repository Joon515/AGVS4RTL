"""LangGraph State Schema for AGVS4RTL workflow.

This module defines the complete state structure used across all workflow stages,
from pre-processing to architecture design to code generation and verification.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class AGVSState(TypedDict, total=False):
    """Complete LangGraph State for AGVS4RTL workflow.
    
    This state is passed between all agents in the workflow:
    - Parser Agent: Writes intent, constraints, metadata
    - Architect Agent: Writes architecture
    - PPA Estimator: Writes ppa
    - Manager Agent: Writes modules, tests, retry_count
    - Coverage Analyzer: Writes coverage, errors
    
    All fields are optional (total=False) to support incremental state building.
    """
    
    # ==================== Raw Request Stage ====================
    natural_language: str
    """Original user requirement text."""

    language: str
    """Input language hint (e.g., zh/en)."""

    source: str
    """Input source tag (e.g., tui/api/smoke)."""

    # ==================== Pre-processing Stage ====================
    intent: Dict[str, Any]
    """Design intent extracted from natural language.
    
    Schema:
        {
            "summary": str,              # Requirements summary
            "target_language": str,       # "verilog" | "systemverilog"
            "clock": Optional[str],       # Clock signal name
            "reset": Optional[str],       # Reset signal name
            "interfaces": List[str]       # Interface keywords (e.g., ["axi-lite"])
        }
    """
    
    constraints: Dict[str, List[Dict[str, Any]]]
    """Hard and soft constraints.
    
    Schema:
        {
            "hard": [{"name": str, "value": Any, "priority": int}],
            "soft": [{"name": str, "value": Any, "priority": int}]
        }
    """
    
    metadata: Dict[str, Any]
    """Request metadata.
    
    Schema:
        {
            "request_id": str,            # UUID
            "created_at": str,            # ISO 8601 timestamp
            "language": str,              # "zh" | "en"
            "source": str,                # "tui" | "api"
            "workflow_version": str       # e.g., "v1.0"
        }
    """
    
    # ==================== Architecture Stage ====================
    architecture: Dict[str, Any]
    """Module hierarchy and port specifications.
    
    Schema:
        {
            "version": int,
            "hierarchy": {
                "top": {...},             # Top-level module
                "modules": [...]          # Sub-modules list
            },
            "interfaces": [...]           # Interface definitions
        }
    
    See: docs/spec/ports-and-hierarchy.md
    """
    
    ppa: Dict[str, Any]
    """Performance, Power, Area estimation report.
    
    Schema:
        {
            "version": int,
            "estimated_at": str,
            "area": {...},
            "power": {...},
            "timing": {...},
            "feasibility": "high" | "medium" | "low",
            "warnings": [...]
        }
    
    See: docs/ppa/report-format.md
    """
    
    # ==================== Verification Stage ====================
    coverage: Dict[str, Any]
    """Coverage metrics and thresholds.
    
    Schema:
        {
            "code_coverage": {...},
            "functional_coverage": {...},
            "assertion_coverage": {...},
            "thresholds": {...},
            "status": "pass" | "fail"
        }
    """
    
    errors: List[Dict[str, Any]]
    """Structured error reports from verification.
    
    Schema:
        [
            {
                "module": str,
                "type": "syntax_error" | "timing_violation" | "functional_error",
                "severity": "error" | "warning" | "info",
                "message": str,
                "file": str,
                "line": int,
                "column": int,
                "suggestion": str
            }
        ]
    """
    
    # ==================== Control & Versioning ====================
    retry_count: Dict[str, int]
    """Retry counter per module.
    
    Schema:
        {
            "module_name": retry_count,
            "global": total_retries
        }
    """
    
    loop_budget: Dict[str, Any]
    """Iteration budget for auto-optimization.
    
    Schema:
        {
            "max_iterations": int,
            "current_iteration": int,
            "remaining": int,
            "auto_optimize": bool,
            "stop_on_no_improvement": bool,
            "no_improvement_threshold": int
        }
    """
    
    versions: List[Dict[str, Any]]
    """Version history for iterative improvements.
    
    Schema:
        [
            {
                "version": int,
                "timestamp": str,
                "changes": str,
                "ppa_snapshot": {...},
                "coverage_snapshot": {...},
                "status": "baseline" | "improved" | "degraded",
                "improvement": str (optional)
            }
        ]
    """
    
    # ==================== Generation Stage ====================
    modules: Dict[str, Dict[str, Any]]
    """Module generation status and file paths.
    
    Schema:
        {
            "module_name": {
                "status": "pending" | "in_progress" | "completed" | "failed",
                "file_path": Optional[str],
                "generated_at": Optional[str],
                "lines_of_code": Optional[int],
                "retry_count": int
            }
        }
    """
    
    tests: Dict[str, Dict[str, Any]]
    """Test generation status.
    
    Schema:
        {
            "module_name": {
                "status": "pending" | "completed" | "failed",
                "test_file": Optional[str],
                "framework": "cocotb" | "pyuvm",
                "test_cases": Optional[int]
            }
        }
    """

    generated_code: Dict[str, Any]
    """Generated HDL code artifacts.

    Schema:
        {
            "language": "verilog" | "systemverilog",
            "kind": "framework" | "full",
            "model": str,
            "generated_at": str,
            "content": str
        }
    """

    round_outputs: List[Dict[str, Any]]
    """Per-stage output history for multi-round traceability.

    Schema:
        [
            {
                "round": int,
                "stage": str,
                "model": str,
                "timestamp": str,
                "output": Dict[str, Any]
            }
        ]
    """

    verification: Dict[str, Any]
    """Requirement-code consistency verification report.

    Schema:
        {
            "status": "pass" | "warn" | "fail",
            "consistency_score": int,
            "summary": str,
            "issues": [
                {
                    "type": str,
                    "severity": "high" | "medium" | "low",
                    "message": str,
                    "evidence": str
                }
            ],
            "verified_at": str,
            "model": str
        }
    """


def create_initial_state(
    intent: Dict[str, Any],
    constraints: Dict[str, List[Dict[str, Any]]],
    metadata: Dict[str, Any],
) -> AGVSState:
    """Create an initial state from pre-processing output.
    
    Args:
        intent: Design intent from Parser Agent
        constraints: Hard/soft constraints
        metadata: Request metadata
    
    Returns:
        Initial AGVSState with pre-processing fields populated
    """
    return AGVSState(
        intent=intent,
        constraints=constraints,
        metadata=metadata,
        retry_count={"global": 0},
        loop_budget={
            "max_iterations": 10,
            "current_iteration": 0,
            "remaining": 10,
            "auto_optimize": True,
            "stop_on_no_improvement": True,
            "no_improvement_threshold": 2,
        },
        versions=[],
        modules={},
        tests={},
        errors=[],
        round_outputs=[],
    )
