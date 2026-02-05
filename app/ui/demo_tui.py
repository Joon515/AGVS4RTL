#!/usr/bin/env python3
"""Interactive demo of TUI dashboard components."""

import sys
import json
from pathlib import Path

sys.path.insert(0, '/app/app')

from ui.tui import TUIApp

# Create sample tasks data
sample_tasks = [
    {"name": "预处理需求", "status": "success", "duration": "2.3s", "loops": "1"},
    {"name": "架构设计", "status": "in_progress", "duration": "5.1s", "loops": "2"},
    {"name": "模块生成", "status": "not_started", "duration": "-", "loops": "-"},
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
