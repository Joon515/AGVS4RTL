#!/usr/bin/env python3
"""Interactive demo of TUI dashboard components."""

import sys
import json
from pathlib import Path

sys.path.insert(0, '/app/app')

from ui.tui import TUIApp
from ui.config_store import ConfigStore

# Create sample tasks data
sample_tasks = [
    {"name": "预处理需求", "status": "success", "duration": "2.3s", "loops": "1"},
    {"name": "架构设计", "status": "in_progress", "duration": "5.1s", "loops": "2"},
    {"name": "模块生成", "status": "failed", "duration": "1.2s", "loops": "3"},
    {"name": "单元测试", "status": "not_started", "duration": "-", "loops": "-"},
]

# Create sample architecture
sample_arch = """
top_module
├── control_unit
│   ├── decoder
│   └── fsm
└── datapath
    ├── alu
    ├── register_file
    └── memory_interface
"""

def setup_demo_data():
    """Setup demo data files."""
    workspace = Path("/app/data/workspace")
    workspace.mkdir(parents=True, exist_ok=True)
    
    # Save tasks
    tasks_file = workspace / "tasks.json"
    tasks_file.write_text(json.dumps(sample_tasks, ensure_ascii=False, indent=2))
    
    # Save architecture
    arch_file = workspace / "architecture.txt"
    arch_file.write_text(sample_arch)

    config_store = ConfigStore(Path("/app"))
    config = config_store.load_config()
    config["loop"] = {"global_loop_budget": 3, "retry_count_max": 2}
    config["agents"] = {
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
    }
    config_store.save_config(config)
    
    print("✅ Demo data setup complete")
    print(f"   - Tasks: {tasks_file}")
    print(f"   - Architecture: {arch_file}")

def demo_dashboard_render():
    """Demo the dashboard rendering."""
    print("\n" + "=" * 60)
    print("📊 TUI Dashboard Demo")
    print("=" * 60)
    
    app = TUIApp(workspace_root=Path("/app"))
    
    # Render each component separately
    print("\n1️⃣  Tasks Table:")
    print("-" * 60)
    tasks = app._load_tasks()
    table = app._render_tasks_table(tasks)
    from rich.console import Console
    console = Console()
    console.print(table)
    
    print("\n2️⃣  Parameters Panel:")
    print("-" * 60)
    params_panel = app._render_params_panel()
    console.print(params_panel)
    
    print("\n3️⃣  Architecture Panel:")
    print("-" * 60)
    arch = app._load_architecture()
    arch_panel = app._render_arch_panel(arch)
    console.print(arch_panel)
    
    print("\n4️⃣  Logs Panel:")
    print("-" * 60)
    logs = app._load_logs()
    logs_panel = app._render_logs_panel(logs)
    console.print(logs_panel)

def main():
    """Run the demo."""
    setup_demo_data()
    demo_dashboard_render()
    
    print("\n" + "=" * 60)
    print("✅ Demo completed!")
    print("=" * 60)
    print("\n💡 提示：在交互式终端中运行 TUI:")
    print("   docker exec -it hdl_agent_core python3 /app/app/main.py")

if __name__ == "__main__":
    main()
