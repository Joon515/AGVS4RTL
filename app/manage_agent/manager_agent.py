"""Manager Agent for module orchestration and state progression.

This module implements a static, deterministic manager for the current version.
It focuses on:
1. Module/test state initialization
2. Bottom-up scheduling (leaf -> mid -> top)
3. Retry and loop budget bookkeeping
4. Deferred graph-validation state writeback (AST-only boundary)

Non-static tests and graph-structure execution are intentionally deferred to the
next version, while preserving AST-based structured inputs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


class ManagerAgent:
    """Static manager that orchestrates module generation readiness."""

    RETRY_LIMIT = 3

    def orchestrate(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Orchestrate module-level generation plan.

        Args:
            state: Current workflow state.

        Returns:
            Partial state update for manager-owned fields.
        """
        architecture = state.get("architecture", {})
        hierarchy = architecture.get("hierarchy", {})

        modules_state = self._initialize_modules_state(state.get("modules", {}), hierarchy)
        tests_state = self._initialize_tests_state(state.get("tests", {}), hierarchy)

        retry_count = dict(state.get("retry_count", {"global": 0}))
        retry_count = self._apply_error_feedback(retry_count, state.get("errors", []))

        loop_budget = self._update_loop_budget(state.get("loop_budget", {}))
        execution_plan = self._build_execution_plan(hierarchy)

        next_module, manager_status = self._select_next_module(
            modules_state=modules_state,
            execution_plan=execution_plan,
            retry_count=retry_count,
            loop_budget=loop_budget,
        )

        if next_module:
            module_record = modules_state.setdefault(next_module, {})
            if module_record.get("status") == "pending":
                module_record["status"] = "in_progress"

        architecture_validation = self._build_validation_stub(state)

        manager_summary = {
            "status": manager_status,
            "next_module": next_module,
            "execution_plan": execution_plan,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "version_scope": "static_only_v1",
        }

        return {
            "modules": modules_state,
            "tests": tests_state,
            "retry_count": retry_count,
            "loop_budget": loop_budget,
            "architecture_validation": architecture_validation,
            "manager": manager_summary,
        }

    def _initialize_modules_state(
        self,
        existing: Dict[str, Dict[str, Any]],
        hierarchy: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """Initialize module generation state from architecture hierarchy."""
        modules_state = dict(existing)

        for module_name, module_type in self._list_all_modules(hierarchy):
            if module_name not in modules_state:
                modules_state[module_name] = {
                    "status": "pending",
                    "type": module_type,
                    "file_path": None,
                    "generated_at": None,
                    "lines_of_code": None,
                    "retry_count": 0,
                }
            else:
                modules_state[module_name].setdefault("status", "pending")
                modules_state[module_name].setdefault("type", module_type)
                modules_state[module_name].setdefault("file_path", None)
                modules_state[module_name].setdefault("generated_at", None)
                modules_state[module_name].setdefault("lines_of_code", None)
                modules_state[module_name].setdefault("retry_count", 0)

        return modules_state

    def _initialize_tests_state(
        self,
        existing: Dict[str, Dict[str, Any]],
        hierarchy: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """Initialize test generation state for each module."""
        tests_state = dict(existing)

        for module_name, _ in self._list_all_modules(hierarchy):
            if module_name not in tests_state:
                tests_state[module_name] = {
                    "status": "pending",
                    "test_file": None,
                    "framework": "pyuvm",
                    "test_cases": None,
                }
            else:
                tests_state[module_name].setdefault("status", "pending")
                tests_state[module_name].setdefault("test_file", None)
                tests_state[module_name].setdefault("framework", "pyuvm")
                tests_state[module_name].setdefault("test_cases", None)

        return tests_state

    def _list_all_modules(self, hierarchy: Dict[str, Any]) -> List[Tuple[str, str]]:
        """Return all modules as (name, type), including top."""
        items: List[Tuple[str, str]] = []

        top = hierarchy.get("top", {})
        top_name = top.get("name")
        if top_name:
            items.append((top_name, top.get("type", "top")))

        for module in hierarchy.get("modules", []):
            module_name = module.get("name")
            if module_name:
                items.append((module_name, module.get("type", "leaf")))

        return items

    def _build_execution_plan(self, hierarchy: Dict[str, Any]) -> List[str]:
        """Build bottom-up execution plan ordered by module type."""
        grouped = {"leaf": [], "mid": [], "ip": [], "top": [], "other": []}
        for module_name, module_type in self._list_all_modules(hierarchy):
            if module_type in grouped:
                grouped[module_type].append(module_name)
            else:
                grouped["other"].append(module_name)

        return (
            sorted(grouped["leaf"])
            + sorted(grouped["mid"])
            + sorted(grouped["ip"])
            + sorted(grouped["top"])
            + sorted(grouped["other"])
        )

    def _apply_error_feedback(
        self,
        retry_count: Dict[str, int],
        errors: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """Apply structured error feedback into retry counters.

        Syntax errors are not counted per current retry policy.
        """
        updated = dict(retry_count)
        updated.setdefault("global", 0)

        for error in errors:
            module_name = error.get("module")
            error_type = error.get("type", "")

            if not module_name or error_type == "syntax_error":
                continue

            updated[module_name] = updated.get(module_name, 0) + 1
            updated["global"] += 1

        return updated

    def _update_loop_budget(self, loop_budget: Dict[str, Any]) -> Dict[str, Any]:
        """Update loop budget for one manager cycle."""
        budget = dict(loop_budget)
        max_iterations = int(budget.get("max_iterations", 10))
        current_iteration = int(budget.get("current_iteration", 0))

        if current_iteration < max_iterations:
            current_iteration += 1

        budget["max_iterations"] = max_iterations
        budget["current_iteration"] = current_iteration
        budget["remaining"] = max(0, max_iterations - current_iteration)
        budget.setdefault("auto_optimize", True)
        budget.setdefault("stop_on_no_improvement", True)
        budget.setdefault("no_improvement_threshold", 2)
        return budget

    def _select_next_module(
        self,
        modules_state: Dict[str, Dict[str, Any]],
        execution_plan: List[str],
        retry_count: Dict[str, int],
        loop_budget: Dict[str, Any],
    ) -> Tuple[str | None, str]:
        """Select next module based on status, retry limit and budget."""
        if int(loop_budget.get("remaining", 0)) <= 0:
            return None, "stopped_budget_exhausted"

        for module_name in execution_plan:
            status = modules_state.get(module_name, {}).get("status", "pending")
            retries = int(retry_count.get(module_name, 0))
            modules_state[module_name]["retry_count"] = retries

            if retries >= self.RETRY_LIMIT:
                modules_state[module_name]["status"] = "failed"
                continue

            if status in ["pending", "failed"]:
                return module_name, "ready_for_generation"

        return None, "all_modules_settled"

    def _build_validation_stub(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Build deferred validation payload with AST boundary preserved."""
        ast_extraction = state.get("ast_extraction")

        return {
            "status": "deferred",
            "scope": "graph_and_non_static_tests_next_version",
            "method_boundary": {
                "structured_input": "ast",
                "regex_for_semantics": False,
            },
            "ast_context_available": bool(ast_extraction),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


def manager_orchestration_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node function for manager orchestration stage."""
    manager = ManagerAgent()
    return manager.orchestrate(state)
