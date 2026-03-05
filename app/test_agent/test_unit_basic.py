"""Unit tests for TestAgent static generation behavior."""

from __future__ import annotations

from pathlib import Path

from app.test_agent.test_agent import TestAgent


def test_test_agent_generates_templates_and_state(tmp_path: Path) -> None:
    """Test that TestAgent writes template files and state fields."""
    agent = TestAgent(
        workspace_root=str(tmp_path),
        sandbox_container="sandbox_not_running_for_unit_test",
    )

    state = {
        "intent": {
            "clock": "clk",
            "reset": "rst_n",
        },
        "architecture": {
            "hierarchy": {
                "top": {
                    "name": "regfile_top",
                    "type": "top",
                },
                "modules": [
                    {"name": "addr_decoder", "type": "leaf"},
                    {"name": "register_bank", "type": "leaf"},
                ],
            },
            "interfaces": [
                {
                    "name": "s_axi",
                    "protocol": "AXI4-Lite",
                }
            ],
        },
        "tests": {},
        "errors": [],
    }

    update = agent.generate(state)

    tests_state = update.get("tests", {})
    assert tests_state["regfile_top"]["status"] == "completed"
    assert tests_state["addr_decoder"]["status"] == "completed"
    assert tests_state["register_bank"]["status"] == "completed"

    top_test_file = tmp_path / "testbench" / "integration" / "test_regfile_top_pyuvm.py"
    unit_test_file = tmp_path / "testbench" / "unit" / "test_addr_decoder_pyuvm.py"

    assert top_test_file.exists()
    assert unit_test_file.exists()

    coverage = update.get("coverage", {})
    assert coverage.get("status") == "pending"
    assert len(coverage.get("reports", [])) == 3
    assert update.get("test_manager", {}).get("sandbox_available") is False

    assert update.get("errors") == []
