"""Docker integration test for TestAgent sandbox simulation flow.

This script is intended to run inside the agent-core container and validates that:
1) TestAgent generates DUT/test/runner assets under shared workspace
2) Sandbox container executes Verilator + pyuvm simulation
3) State is updated with pass/fail execution status and coverage reports
"""

from __future__ import annotations

import json
import sys

try:
    from ._bootstrap import ensure_project_root
except ImportError:
    from _bootstrap import ensure_project_root

PROJECT_ROOT = ensure_project_root()

from app.test_agent.test_agent import TestAgent


def main() -> int:
    """Run one integration scenario against sandbox runtime."""
    workspace_root = PROJECT_ROOT / "data" / "workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)

    state = {
        "intent": {
            "clock": "clk",
            "reset": "rst_n",
        },
        "architecture": {
            "hierarchy": {
                "top": {
                    "name": "demo_top",
                    "type": "top",
                },
                "modules": [
                    {"name": "demo_leaf", "type": "leaf"},
                ],
            },
            "interfaces": [
                {"name": "simple_if", "protocol": "custom"},
            ],
        },
        "tests": {},
        "errors": [],
    }

    agent = TestAgent(workspace_root=str(workspace_root), sandbox_container="hdl_sandbox")
    update = agent.generate(state)

    print(json.dumps(update, ensure_ascii=False, indent=2))

    reports = update.get("coverage", {}).get("reports", [])
    if not reports:
        return 1

    non_pass = [item for item in reports if item.get("status") != "pass"]
    return 1 if non_pass else 0


if __name__ == "__main__":
    raise SystemExit(main())
