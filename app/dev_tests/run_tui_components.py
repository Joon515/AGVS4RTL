#!/usr/bin/env python3
"""Test TUI initialization, menu structure, and input handling."""

import sys

try:
    from ._bootstrap import ensure_project_root
except ImportError:
    from _bootstrap import ensure_project_root

PROJECT_ROOT = ensure_project_root()

from app.ui.tui import TUIApp
from app.pre_agent import Preprocessor


def test_tui_initialization():
    """Test TUI app initialization."""
    print("=" * 60)
    print("Testing TUI Initialization")
    print("=" * 60)
    
    app = TUIApp(workspace_root=PROJECT_ROOT)
    
    print("\n✅ TUI App initialized")
    print(f"   Workspace: {app.workspace_root}")
    print(f"   Tasks file: {app.tasks_file}")
    print(f"   Architecture file: {app.architecture_file}")
    print(f"   Logs dir: {app.logs_dir}")
    
    # Check agent config keys
    print(f"\n🤖 Agent config has {len(app.agent_config)} agents:")
    for agent_name, agent_cfg in app.agent_config.items():
        print(f"   - {agent_name}")
        print(f"     model: {agent_cfg.get('model', 'N/A')}")
        print(f"     temperature: {agent_cfg.get('temperature', 'N/A')}")
    
    return True


def test_menu_items():
    """Test menu item display."""
    print("\n" + "=" * 60)
    print("Testing Menu Items")
    print("=" * 60)
    
    # Hardcoded menu items from TUIApp._display_menu()
    menu_items = [
        "1️⃣  输入需求 (Input)",
        "2️⃣  查看日志 (Logs)",
        "3️⃣  配置参数 (Config)",
        "4️⃣  退出 (Exit)",
    ]
    
    print("\n📋 Menu items:")
    for item in menu_items:
        print(f"   {item}")
    
    return True


def test_preprocessor_integration():
    """Test preprocessor as part of TUI input."""
    print("\n" + "=" * 60)
    print("Testing Preprocessor Integration")
    print("=" * 60)
    
    # Simulate TUI input processing
    user_input = "实现一个 16 位乘法器,工作频率 200MHz,最小化面积"
    
    print(f"\n👤 User input: {user_input}")
    
    # Process through preprocessor
    result = Preprocessor.from_text(
        text=user_input,
        language="zh",
        hard_constraints={"freq": "200MHz"},
        soft_constraints={"area": "min"},
        target_language="verilog",
        interfaces=["clk", "rst"],
        clock="clk",
        reset="rst_n",
        source="tui",
    )
    
    print(f"\n📦 Preprocessed output:")
    print(f"   Request ID: {result.request_id}")
    print(f"   Intent summary: {result.intent.summary}")
    print(f"   Target language: {result.intent.target_language}")
    print(f"   Hard constraints: {result.constraints.hard}")
    print(f"   Soft constraints: {result.constraints.soft}")
    
    # Convert to state
    state = result.to_state()
    print(f"\n🔄 State payload keys: {list(state.keys())}")
    
    return True


def test_log_management():
    """Test log file discovery and display."""
    print("\n" + "=" * 60)
    print("Testing Log Management")
    print("=" * 60)
    
    app = TUIApp(workspace_root=PROJECT_ROOT)
    
    # Load logs
    logs = app._load_logs()
    print(f"\n📝 Found {len(logs)} log files:")
    for idx, log_file in enumerate(logs[:5], 1):
        print(f"   {idx}. {log_file}")
    
    if len(logs) > 5:
        print(f"   ... and {len(logs) - 5} more")
    
    return True


def test_architecture_display():
    """Test architecture loading."""
    print("\n" + "=" * 60)
    print("Testing Architecture Display")
    print("=" * 60)
    
    app = TUIApp(workspace_root=PROJECT_ROOT)
    
    arch = app._load_architecture()
    print(f"\n🏗️  Architecture content ({len(arch)} chars):")
    print(arch[:200] + ("..." if len(arch) > 200 else ""))
    
    return True


def test_tasks_display():
    """Test tasks loading."""
    print("\n" + "=" * 60)
    print("Testing Tasks Display")
    print("=" * 60)
    
    app = TUIApp(workspace_root=PROJECT_ROOT)
    
    tasks = app._load_tasks()
    print(f"\n✅ Loaded {len(tasks)} tasks:")
    for task in tasks[:3]:
        print(f"   - {task}")
    
    if len(tasks) > 3:
        print(f"   ... and {len(tasks) - 3} more")
    
    return True


if __name__ == "__main__":
    tests = [
        ("TUI初始化", test_tui_initialization),
        ("菜单项", test_menu_items),
        ("预处理集成", test_preprocessor_integration),
        ("日志管理", test_log_management),
        ("架构显示", test_architecture_display),
        ("任务显示", test_tasks_display),
    ]
    
    print("\n🧪 Running TUI Component Tests\n")
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, "✅ PASSED"))
        except Exception as e:
            results.append((test_name, f"❌ FAILED: {e}"))
            print(f"\n❌ Error in {test_name}: {e}\n")
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for test_name, result in results:
        print(f"{result:20} {test_name}")
    
    passed = sum(1 for _, r in results if "✅" in r)
    total = len(results)
    print(f"\n总计: {passed}/{total} 通过")
    
    sys.exit(0 if passed == total else 1)
