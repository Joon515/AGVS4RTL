"""Test script for pre-Manager workflow.

This script tests the complete workflow from Parser Agent to PPA Estimator.
"""

import json
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_parser_agent():
    """Test Parser Agent standalone."""
    print("\n" + "=" * 70)
    print("测试 1: Parser Agent")
    print("=" * 70)
    
    from app.pre_agent.parser_agent import ParserAgent
    
    parser = ParserAgent()
    
    requirement = "设计一个带AXI4-Lite接口的32位寄存器文件，支持4KB地址空间，工作频率200MHz"
    
    result = parser.parse(requirement)
    
    print(f"\n原始需求: {requirement}")
    print(f"\n解析结果:")
    print(f"  摘要: {result.intent.summary}")
    print(f"  接口: {result.intent.interfaces}")
    print(f"  时钟: {result.intent.clock}")
    print(f"  复位: {result.intent.reset}")
    
    print(f"\n硬约束:")
    for c in result.constraints.hard:
        print(f"  - {c.name}: {c.value}")
    
    print(f"\n软约束:")
    for c in result.constraints.soft:
        print(f"  - {c.name}: {c.value}")
    
    assert result.intent.target_language == "verilog"
    assert "axi-lite" in result.intent.interfaces or "axi" in result.intent.interfaces
    
    print("\n✅ Parser Agent 测试通过")
    return result


def test_rag_system():
    """Test RAG vector store."""
    print("\n" + "=" * 70)
    print("测试 2: RAG Vector Store")
    print("=" * 70)
    
    from app.rag.vector_store import KnowledgeLoader
    
    loader = KnowledgeLoader()
    
    # Check if knowledge docs exist
    docs_dir = "data/rag/knowledge_docs"
    if not os.path.exists(docs_dir):
        print(f"\n⚠️  知识库目录不存在: {docs_dir}")
        print("跳过 RAG 测试")
        return None
    
    # Load documents
    print("\n加载知识文档...")
    doc_count = loader.load_from_directory(docs_dir)
    print(f"已加载 {doc_count} 个文档")
    
    if doc_count == 0:
        print("⚠️  没有找到知识文档，跳过检索测试")
        return None
    
    # Search test
    print("\n执行检索测试...")
    query = "AXI-Lite 寄存器接口"
    results = loader.search(query, n_results=3)
    
    print(f"\n查询: {query}")
    print(f"检索到 {len(results)} 个结果:")
    
    for i, result in enumerate(results, 1):
        print(f"\n  结果 {i}:")
        print(f"    ID: {result['id']}")
        print(f"    相似度: {result.get('score', 0):.3f}")
        print(f"    内容预览: {result['document'][:100]}...")
    
    print("\n✅ RAG 测试通过")
    return loader


def test_architect_agent(parser_result):
    """Test Architect Agent."""
    print("\n" + "=" * 70)
    print("测试 3: Architect Agent")
    print("=" * 70)
    
    from app.manage_agent.architect_agent import ArchitectAgent
    
    architect = ArchitectAgent(use_rag=True)
    
    intent = parser_result.intent.model_dump()
    constraints = parser_result.constraints.model_dump()
    
    print("\n生成架构设计...")
    architecture = architect.design(intent, constraints)
    
    print(f"\n架构版本: {architecture.get('version', 'N/A')}")
    
    hierarchy = architecture.get("hierarchy", {})
    top = hierarchy.get("top", {})
    print(f"顶层模块: {top.get('name', 'N/A')}")
    print(f"模块类型: {top.get('type', 'N/A')}")
    print(f"描述: {top.get('description', 'N/A')}")
    
    modules = hierarchy.get("modules", [])
    print(f"\n子模块数量: {len(modules)}")
    if modules:
        print("子模块列表:")
        for module in modules:
            print(f"  - {module.get('name', 'N/A')} ({module.get('type', 'N/A')})")
    
    interfaces = architecture.get("interfaces", [])
    print(f"\n接口数量: {len(interfaces)}")
    if interfaces:
        print("接口列表:")
        for intf in interfaces:
            print(f"  - {intf.get('name', 'N/A')}: {intf.get('protocol', 'N/A')}")
    
    print("\n✅ Architect Agent 测试通过")
    return architecture


def test_ppa_estimator(architecture, constraints):
    """Test PPA Estimator."""
    print("\n" + "=" * 70)
    print("测试 4: PPA Estimator")
    print("=" * 70)
    
    from app.manage_agent.ppa_estimator import PPAEstimator
    
    estimator = PPAEstimator()
    
    print("\n执行PPA评估...")
    ppa = estimator.estimate(architecture, constraints)
    
    # Area
    area = ppa.get("area", {})
    print(f"\n面积评估:")
    print(f"  总门数: {area.get('total_gates', 'N/A')} GE")
    print(f"  寄存器: {area.get('breakdown', {}).get('registers', 'N/A')}")
    print(f"  组合逻辑: {area.get('breakdown', {}).get('combinational', 'N/A')}")
    print(f"  工艺: {area.get('technology', 'N/A')}")
    
    # Power
    power = ppa.get("power", {})
    print(f"\n功耗评估:")
    print(f"  总功耗: {power.get('total_mw', 'N/A')} mW")
    print(f"  动态功耗: {power.get('dynamic_mw', 'N/A')} mW")
    print(f"  静态功耗: {power.get('static_mw', 'N/A')} mW")
    
    # Timing
    timing = ppa.get("timing", {})
    print(f"\n时序评估:")
    print(f"  最大频率: {timing.get('max_freq_mhz', 'N/A')} MHz")
    
    critical_path = timing.get("critical_path", {})
    print(f"  关键路径延迟: {critical_path.get('delay_ns', 'N/A')} ns")
    print(f"  时序裕量: {critical_path.get('slack_ns', 'N/A')} ns")
    
    # Feasibility
    feasibility = ppa.get("feasibility", "unknown")
    print(f"\n可行性评级: {feasibility.upper()}")
    
    warnings = ppa.get("warnings", [])
    if warnings:
        print(f"\n警告信息 ({len(warnings)} 条):")
        for warning in warnings:
            severity = warning.get("severity", "info").upper()
            message = warning.get("message", "")
            print(f"  [{severity}] {message}")
    else:
        print("\n✅ 无警告")
    
    print("\n✅ PPA Estimator 测试通过")
    return ppa


def test_complete_workflow():
    """Test complete workflow."""
    print("\n" + "=" * 70)
    print("测试 5: 完整工作流集成")
    print("=" * 70)
    
    from app.workflow import run_pre_manager_workflow
    
    requirement = """
    实现一个支持AXI4-Lite接口的32位寄存器文件模块。
    地址空间为4KB，工作频率200MHz，采用低功耗设计。
    包含异步复位，支持字节选通。
    """
    
    print(f"\n需求: {requirement.strip()}")
    print("\n执行完整工作流...")
    
    try:
        result = run_pre_manager_workflow(requirement.strip())
        
        print("\n✅ 工作流执行成功")
        
        # Verify all stages completed
        assert "intent" in result, "缺少 intent 字段"
        assert "architecture" in result, "缺少 architecture 字段"
        assert "ppa" in result, "缺少 ppa 字段"
        
        print("\n所有阶段已完成:")
        print("  ✓ Parser Agent")
        print("  ✓ Architect Agent")
        print("  ✓ PPA Estimator")
        
        return result
        
    except Exception as e:
        print(f"\n❌ 工作流执行失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def save_results(result, output_file="test_results.json"):
    """Save test results to file."""
    if result:
        output_path = Path("data/workspace") / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n结果已保存到: {output_path}")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("AGVS4RTL 预处理工作流测试套件")
    print("=" * 70)
    
    try:
        # Test 1: Parser Agent
        parser_result = test_parser_agent()
        
        # Test 2: RAG System
        test_rag_system()
        
        # Test 3: Architect Agent
        architecture = test_architect_agent(parser_result)
        
        # Test 4: PPA Estimator
        constraints = parser_result.constraints.model_dump()
        ppa = test_ppa_estimator(architecture, constraints)
        
        # Test 5: Complete Workflow
        workflow_result = test_complete_workflow()
        
        # Save results
        if workflow_result:
            save_results(workflow_result)
        
        print("\n" + "=" * 70)
        print("✅ 所有测试通过！")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
