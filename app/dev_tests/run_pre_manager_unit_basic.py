"""Unit tests for pre-Manager modules (no LLM required).

This test suite validates the basic functionality of all modules
without requiring OpenAI API keys.
"""

import sys

try:
    from ._bootstrap import ensure_project_root
except ImportError:
    from _bootstrap import ensure_project_root

PROJECT_ROOT = ensure_project_root()


def test_state_schema():
    """Test State Schema structure."""
    print("\n" + "=" * 70)
    print("测试 1: State Schema 结构验证")
    print("=" * 70)
    
    from app.manage_agent.state_schema import AGVSState, create_initial_state
    
    # Test create_initial_state
    intent = {
        "summary": "测试需求",
        "target_language": "verilog",
        "clock": "clk",
        "reset": "rst_n",
        "interfaces": ["axi-lite"]
    }
    
    constraints = {
        "hard": [{"name": "freq", "value": "200MHz", "priority": 0}],
        "soft": [{"name": "area", "value": "minimize", "priority": 1}]
    }
    
    metadata = {
        "request_id": "test-001",
        "created_at": "2026-02-14T10:00:00Z",
        "language": "zh",
        "source": "test"
    }
    
    state = create_initial_state(intent, constraints, metadata)
    
    # Verify state structure
    assert "intent" in state
    assert "constraints" in state
    assert "metadata" in state
    assert "retry_count" in state
    assert "loop_budget" in state
    assert state["retry_count"]["global"] == 0
    assert state["loop_budget"]["max_iterations"] == 10
    
    print("\n✅ State Schema 结构正确")
    print(f"  - intent: {state['intent']['summary']}")
    print(f"  - 硬约束数量: {len(state['constraints']['hard'])}")
    print(f"  - 迭代预算: {state['loop_budget']['max_iterations']}")
    
    return True


def test_preprocessor():
    """Test Preprocessor from existing module."""
    print("\n" + "=" * 70)
    print("测试 2: Preprocessor 数据结构")
    print("=" * 70)
    
    from app.pre_agent.structure_request import Preprocessor
    
    # Test from_text method
    result = Preprocessor.from_text(
        text="设计一个AXI寄存器文件",
        language="zh",
        hard_constraints={"freq": "200MHz", "data_width": 32},
        soft_constraints={"area": "minimize"},
        target_language="verilog",
        interfaces=["axi-lite"],
        clock="clk",
        reset="rst_n",
        source="test"
    )
    
    # Verify structure
    assert result.intent.summary == "设计一个AXI寄存器文件"
    assert result.intent.target_language == "verilog"
    assert "axi-lite" in result.intent.interfaces
    assert len(result.constraints.hard) == 2
    assert len(result.constraints.soft) == 1
    
    print("\n✅ Preprocessor 测试通过")
    print(f"  - 需求ID: {result.request_id}")
    print(f"  - 接口: {result.intent.interfaces}")
    print(f"  - 硬约束: {[c.name for c in result.constraints.hard]}")
    
    # Test to_state conversion
    state = result.to_state()
    assert "intent" in state
    assert "constraints" in state
    assert "metadata" in state
    
    print("  - to_state() 转换成功")
    
    return True


def test_ppa_estimator():
    """Test PPA Estimator with mock architecture."""
    print("\n" + "=" * 70)
    print("测试 3: PPA Estimator 评估逻辑")
    print("=" * 70)
    
    from app.manage_agent.ppa_estimator import PPAEstimator
    
    # Mock architecture
    architecture = {
        "version": 1,
        "hierarchy": {
            "top": {
                "name": "axi_register_file",
                "type": "top",
                "description": "AXI寄存器文件",
                "children": ["axi_slave", "reg_array"],
                "ports": {}
            },
            "modules": [
                {
                    "name": "axi_slave",
                    "type": "leaf",
                    "description": "AXI从设备接口",
                    "ports": {},
                    "parameters": {"DATA_WIDTH": 32, "ADDR_WIDTH": 12}
                },
                {
                    "name": "reg_array",
                    "type": "leaf",
                    "description": "寄存器阵列",
                    "ports": {},
                    "parameters": {"NUM_REGS": 1024, "DATA_WIDTH": 32}
                }
            ]
        },
        "interfaces": [
            {
                "name": "s_axi",
                "protocol": "AXI4-Lite",
                "mode": "slave",
                "data_width": 32,
                "addr_width": 12
            }
        ]
    }
    
    # Mock constraints
    constraints = {
        "hard": [
            {"name": "freq", "value": "200MHz", "priority": 0},
            {"name": "data_width", "value": 32, "priority": 0}
        ],
        "soft": [
            {"name": "area", "value": "minimize", "priority": 1}
        ]
    }
    
    # Run estimator
    estimator = PPAEstimator(technology="28nm")
    ppa = estimator.estimate(architecture, constraints)
    
    # Verify PPA structure
    assert "version" in ppa
    assert "area" in ppa
    assert "power" in ppa
    assert "timing" in ppa
    assert "feasibility" in ppa
    assert ppa["feasibility"] in ["high", "medium", "low"]
    
    print("\n✅ PPA Estimator 测试通过")
    print(f"  - 总门数: {ppa['area']['total_gates']} GE")
    print(f"  - 总功耗: {ppa['power']['total_mw']} mW")
    print(f"  - 最大频率: {ppa['timing']['max_freq_mhz']} MHz")
    print(f"  - 可行性: {ppa['feasibility'].upper()}")
    
    if ppa.get("warnings"):
        print(f"  - 警告数量: {len(ppa['warnings'])}")
        for warning in ppa["warnings"][:3]:  # Show first 3
            print(f"    • [{warning['severity']}] {warning['message']}")
    else:
        print("  - 无警告")
    
    return True


def test_rag_module_structure():
    """Test RAG module structure (without actual embedding)."""
    print("\n" + "=" * 70)
    print("测试 4: RAG 模块结构验证")
    print("=" * 70)
    
    try:
        from app.rag.vector_store import RAGVectorStore, KnowledgeLoader
        
        print("\n✅ RAG 模块导入成功")
        print("  - RAGVectorStore 类已定义")
        print("  - KnowledgeLoader 类已定义")
        
        # Test if ChromaDB is available
        try:
            import chromadb
            print("  - ChromaDB 已安装")
        except ImportError:
            print("  ⚠️  ChromaDB 未安装（可选依赖）")
        
        return True
        
    except ImportError as e:
        print(f"\n⚠️  RAG 模块导入失败: {e}")
        return False


def test_parser_agent_structure():
    """Test Parser Agent structure (without LLM call)."""
    print("\n" + "=" * 70)
    print("测试 5: Parser Agent 结构验证")
    print("=" * 70)
    
    from app.pre_agent.parser_agent import ParserAgent
    
    print("\n✅ Parser Agent 类导入成功")
    
    # Test fallback parsing directly (no LLM initialization needed)
    # Create a mock parser instance without __init__
    import types
    parser = types.SimpleNamespace()
    parser._fallback_parse = ParserAgent._fallback_parse.__get__(parser, ParserAgent)
    
    # Test fallback parsing (regex-based)
    result = parser._fallback_parse("设计一个200MHz的AXI寄存器文件，32位数据宽度")
    
    assert "intent" in result
    assert "constraints" in result
    assert result["intent"]["target_language"] == "verilog"
    
    print("  - _fallback_parse() 方法正常（静态方法测试）")
    print(f"  - 识别接口: {result['intent']['interfaces']}")
    print(f"  - 识别约束: {len(result['constraints']['hard'])} 个硬约束")
    
    return True


def test_architect_agent_structure():
    """Test Architect Agent structure (without LLM call)."""
    print("\n" + "=" * 70)
    print("测试 6: Architect Agent 结构验证")
    print("=" * 70)
    
    from app.manage_agent.architect_agent import ArchitectAgent
    
    print("\n✅ Architect Agent 类导入成功")
    
    # Test fallback architecture generation without initialization
    import types
    agent = types.SimpleNamespace()
    agent._fallback_architecture = ArchitectAgent._fallback_architecture.__get__(agent, ArchitectAgent)
    
    intent = {
        "summary": "AXI寄存器文件",
        "target_language": "verilog",
        "interfaces": ["axi-lite"]
    }
    
    fallback_arch = agent._fallback_architecture(intent)
    
    assert "version" in fallback_arch
    assert "hierarchy" in fallback_arch
    assert "interfaces" in fallback_arch
    
    print("  - _fallback_architecture() 方法正常（静态方法测试）")
    print(f"  - 顶层模块: {fallback_arch['hierarchy']['top']['name']}")
    
    return True


def test_workflow_structure():
    """Test workflow structure."""
    print("\n" + "=" * 70)
    print("测试 7: Workflow 工作流结构")
    print("=" * 70)
    
    from app.workflow import create_manager_workflow, create_pre_manager_workflow
    
    # Create workflow graph
    workflow = create_pre_manager_workflow()
    
    print("\n✅ Workflow 创建成功")
    print("  - 工作流图已编译")
    print("  - 包含节点: parser, architect, ppa_estimator")

    manager_workflow = create_manager_workflow()
    assert manager_workflow is not None
    print("  - 扩展节点: manager")
    
    return True


def test_manager_agent_structure():
    """Test Manager Agent static orchestration behavior."""
    print("\n" + "=" * 70)
    print("测试 8: Manager Agent 静态编排")
    print("=" * 70)

    from app.manage_agent.manager_agent import ManagerAgent

    manager = ManagerAgent()

    state = {
        "architecture": {
            "hierarchy": {
                "top": {
                    "name": "axi_register_file",
                    "type": "top",
                    "children": ["axi_slave", "reg_array"],
                },
                "modules": [
                    {"name": "axi_slave", "type": "leaf"},
                    {"name": "reg_array", "type": "leaf"},
                ],
            }
        },
        "ppa": {"feasibility": "high"},
        "retry_count": {"global": 0},
        "loop_budget": {
            "max_iterations": 10,
            "current_iteration": 0,
            "remaining": 10,
        },
        "errors": [],
        "ast_extraction": {"status": "success"},
    }

    update = manager.orchestrate(state)

    assert "modules" in update
    assert "tests" in update
    assert "retry_count" in update
    assert "loop_budget" in update
    assert "architecture_validation" in update
    assert "manager" in update

    summary = update["manager"]
    assert summary["status"] in ["ready_for_generation", "all_modules_settled"]
    assert isinstance(summary["execution_plan"], list)

    print("\n✅ Manager Agent 结构测试通过")
    print(f"  - 管理状态: {summary['status']}")
    print(f"  - 下一模块: {summary.get('next_module')}")
    print(f"  - 计划长度: {len(summary['execution_plan'])}")

    return True


def test_file_structure():
    """Test project file structure."""
    print("\n" + "=" * 70)
    print("测试 9: 项目文件结构完整性")
    print("=" * 70)
    
    # Only check files that should be in /app mount (app/ directory)
    required_files = [
        "app/manage_agent/state_schema.py",
        "app/manage_agent/architect_agent.py",
        "app/manage_agent/manager_agent.py",
        "app/manage_agent/ppa_estimator.py",
        "app/manage_agent/__init__.py",
        "app/pre_agent/parser_agent.py",
        "app/pre_agent/structure_request.py",
        "app/rag/vector_store.py",
        "app/rag/__init__.py",
        "app/workflow.py",
    ]
    
    missing_files = []
    for file_path in required_files:
        full_path = PROJECT_ROOT / file_path
        if not full_path.exists():
            missing_files.append(file_path)
    
    if missing_files:
        print("\n❌ 缺少文件:")
        for f in missing_files:
            print(f"  - {f}")
        return False
    else:
        print("\n✅ 所有必需文件存在")
        print(f"  - 检查了 {len(required_files)} 个文件")
        return True


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("🧪 AGVS4RTL 单元测试套件 (无 LLM 依赖)")
    print("=" * 70)
    
    tests = [
        ("State Schema", test_state_schema),
        ("Preprocessor", test_preprocessor),
        ("PPA Estimator", test_ppa_estimator),
        ("RAG Module", test_rag_module_structure),
        ("Parser Agent", test_parser_agent_structure),
        ("Architect Agent", test_architect_agent_structure),
        ("Workflow", test_workflow_structure),
        ("Manager Agent", test_manager_agent_structure),
        ("File Structure", test_file_structure),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"\n❌ {test_name} 测试失败")
        except Exception as e:
            failed += 1
            print(f"\n❌ {test_name} 测试异常: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("📊 测试结果汇总")
    print("=" * 70)
    print(f"✅ 通过: {passed}/{len(tests)}")
    print(f"❌ 失败: {failed}/{len(tests)}")
    
    if failed == 0:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  有 {failed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
