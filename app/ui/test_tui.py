#!/usr/bin/env python3
"""Test script for TUI functionality.

This script tests the TUI components in non-interactive mode to verify
imports, data structures, and basic functionality.
"""

import sys
import json
from pathlib import Path

# Add parent directory to path to import sibling modules
sys.path.insert(0, '/app/app')

# Import from sibling directories
import pre_agent
import ui

from pre_agent import Preprocessor, DesignIntent, StructuredConstraints
from ui import TUIApp


def test_preprocessor():
    """Test Preprocessor functionality."""
    print("=" * 60)
    print("Testing Preprocessor...")
    print("=" * 60)
    
    result = Preprocessor.from_text(
        text="实现一个 8 位加法器",
        language="zh",
        hard_constraints={"freq": "100MHz"},
        soft_constraints={"area": "min"},
        target_language="verilog",
        interfaces=["clk", "rst"],
        clock="clk",
        reset="rst_n",
        source="test",
    )
    
    print("\n✅ Preprocessor created successfully")
    print(f"   Request ID: {result.request_id}")
    print(f"   Created at: {result.created_at}")
    print(f"   Summary: {result.intent.summary}")
    
    payload = result.to_state()
    print("\n📦 State Payload:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    
    return result


def test_tui_components():
    """Test TUI components without running interactive loop."""
    print("\n" + "=" * 60)
    print("Testing TUI Components...")
    print("=" * 60)
    
    app = TUIApp(workspace_root=Path("/app"))
    print("\n✅ TUIApp initialized successfully")
    print(f"   Workspace root: {app.workspace_root}")
    print(f"   Preset params: {app.params}")
    
    # Test loading tasks
    tasks = app._load_tasks()
    print(f"\n📋 Tasks loaded: {len(tasks)} tasks")
    if tasks:
        for task in tasks:
            print(f"   - {task}")
    
    # Test loading architecture
    arch = app._load_architecture()
    print(f"\n🏗️  Architecture: {arch[:50]}...")
    
    # Test loading logs
    logs = app._load_logs()
    print(f"\n📝 Logs found: {len(logs)} files")
    for log in logs[:3]:
        print(f"   - {log}")
    
    return app


def test_data_models():
    """Test data models."""
    print("\n" + "=" * 60)
    print("Testing Data Models...")
    print("=" * 60)
    
    intent = DesignIntent(
        summary="测试模块",
        target_language="verilog",
        clock="clk",
        reset="rst",
        interfaces=["ahb", "apb"],
    )
    print("\n✅ DesignIntent created:")
    print(f"   {intent.model_dump()}")
    
    constraints = StructuredConstraints(
        hard=[],
        soft=[],
    )
    print("\n✅ StructuredConstraints created:")
    print(f"   {constraints.model_dump()}")


def main():
    """Run all tests."""
    print("\n🚀 AGVS4RTL TUI Test Suite")
    print("=" * 60)
    
    try:
        test_data_models()
        result = test_preprocessor()
        app = test_tui_components()
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        
        # Save test output
        output_dir = Path("/app/data/workspace/test_output")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "preprocessor_test.json"
        output_file.write_text(
            json.dumps(result.to_state(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"\n💾 Test output saved to: {output_file}")
        
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ Test failed: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
