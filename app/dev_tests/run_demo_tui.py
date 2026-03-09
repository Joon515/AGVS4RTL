#!/usr/bin/env python3
"""Interactive demo of TUI dashboard components (development-only)."""

from __future__ import annotations

import json

try:
    from ._bootstrap import ensure_project_root
except ImportError:
    from _bootstrap import ensure_project_root

PROJECT_ROOT = ensure_project_root()

from app.ui.config_store import ConfigStore
from app.ui.tui import TUIApp

# Create sample tasks data
SAMPLE_TASKS = [
    {"name": "预处理需求", "status": "success", "duration": "2.3s", "loops": "1"},
    {"name": "架构设计", "status": "in_progress", "duration": "5.1s", "loops": "2"},
    {"name": "模块生成", "status": "failed", "duration": "1.2s", "loops": "3"},
    {"name": "单元测试", "status": "not_started", "duration": "-", "loops": "-"},
]

# Create sample architecture
SAMPLE_ARCH = """
top_module
├── control_unit
│   ├── decoder
│   └── fsm
└── datapath
    ├── alu
    ├── register_file
    └── memory_interface
"""


def setup_demo_data() -> None:
    """Setup demo data files."""
    workspace = PROJECT_ROOT / "data" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    tasks_file = workspace / "tasks.json"
    tasks_file.write_text(json.dumps(SAMPLE_TASKS, ensure_ascii=False, indent=2), encoding="utf-8")

    arch_file = workspace / "architecture.txt"
    arch_file.write_text(SAMPLE_ARCH, encoding="utf-8")

    # Important: do not mutate runtime config from demo script.
    # We only write a snapshot file for display/reference.
    _ = ConfigStore(PROJECT_ROOT)
    config_snapshot = {
        "loop": {"global_loop_budget": 3, "retry_count_max": 2},
        "agents": {
            "pre_agent": {
                "model": "gpt-4o-mini",
                "top_k": 40,
                "top_p": 0.9,
                "temperature": 0.7,
                "api_key_enc": {"mock": True},
            },
            "architecture_agent": {
                "model": "gpt-4o-mini",
                "top_k": 50,
                "top_p": 0.95,
                "temperature": 0.6,
                "api_key_enc": {"mock": True},
            },
            "manager_agent": {
                "model": "gpt-4o-mini",
                "top_k": 30,
                "top_p": 0.9,
                "temperature": 0.5,
                "api_key_enc": {"mock": True},
            },
            "generate_agent": {
                "model": "gpt-4o-mini",
                "top_k": 40,
                "top_p": 0.9,
                "temperature": 0.7,
                "api_key_enc": {"mock": True},
            },
            "test_agent": {
                "model": "gpt-4o-mini",
                "top_k": 40,
                "top_p": 0.9,
                "temperature": 0.7,
                "api_key_enc": {"mock": True},
            },
            "analyzer_agent": {
                "model": "gpt-4o-mini",
                "top_k": 20,
                "top_p": 0.85,
                "temperature": 0.4,
                "api_key_enc": {"mock": True},
            },
            "integrator_agent": {
                "model": "gpt-4o-mini",
                "top_k": 40,
                "top_p": 0.9,
                "temperature": 0.6,
                "api_key_enc": {"mock": True},
            },
        },
        "note": "demo snapshot only, not applied to runtime config",
    }
    snapshot_file = workspace / "demo_tui_config_snapshot.json"
    snapshot_file.write_text(
        json.dumps(config_snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("Demo data setup complete")
    print(f"  - Tasks: {tasks_file}")
    print(f"  - Architecture: {arch_file}")
    print(f"  - Config snapshot (not applied): {snapshot_file}")


def demo_dashboard_render() -> None:
    """Demo the dashboard rendering."""
    print("\n" + "=" * 60)
    print("TUI Dashboard Demo")
    print("=" * 60)

    app = TUIApp(workspace_root=PROJECT_ROOT)

    print("\n1) Tasks Table:")
    print("-" * 60)
    tasks = app._load_tasks()
    table = app._render_tasks_table(tasks)
    from rich.console import Console

    console = Console()
    console.print(table)

    print("\n2) Parameters Panel:")
    print("-" * 60)
    params_panel = app._render_params_panel()
    console.print(params_panel)

    print("\n3) Architecture Panel:")
    print("-" * 60)
    arch = app._load_architecture()
    arch_panel = app._render_arch_panel(arch)
    console.print(arch_panel)

    print("\n4) Logs Panel:")
    print("-" * 60)
    logs = app._load_logs()
    logs_panel = app._render_logs_panel(logs)
    console.print(logs_panel)


def main() -> None:
    """Run the demo."""
    setup_demo_data()
    demo_dashboard_render()

    print("\n" + "=" * 60)
    print("Demo completed")
    print("=" * 60)
    print("\nHint: run interactive TUI in Docker with:")
    print("  docker exec -it hdl_agent_core python3 /app/app/main.py")


if __name__ == "__main__":
    main()
