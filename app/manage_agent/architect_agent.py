"""Architect Agent for HDL module hierarchy design with RAG support.

This agent generates module hierarchy trees, port specifications, and interface
definitions based on design intent. It uses RAG to retrieve similar design patterns
from the knowledge base.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..rag.vector_store import KnowledgeLoader


class ArchitectAgent:
    """RAG-enhanced architecture design agent."""
    
    # System prompt for architecture design
    SYSTEM_PROMPT = """你是一个硬件架构设计专家，擅长将高层需求转换为分层次的HDL模块结构。

**任务：**
根据设计意图和约束，生成模块层次树（Hierarchy Tree）、端口规范和接口定义。

**设计原则：**
1. **层次化设计**：
   - 顶层模块 (top): 包含所有外部接口
   - 中间层模块 (mid): 组合多个子模块
   - 叶子模块 (leaf): 不包含子模块的基本单元

2. **模块命名**：
   - 使用小写蛇形命名法: `axi_slave`, `fifo_controller`
   - 体现功能: `write_channel`, `address_decoder`
   - 避免过于泛化的名称

3. **端口规范**：
   - 时钟: `clk`, `clk_<domain>`
   - 复位: `rst_n` (低电平有效), `rst` (高电平有效)
   - 接口前缀: AXI-Lite Slave: `s_axi_*`, Master: `m_axi_*`
   - 信号后缀: `_valid`, `_ready`, `_data`, `_addr`

4. **接口定义**：
   - 使用标准协议: AXI4-Lite, AXI-Stream, APB等
   - 明确数据位宽和地址位宽
   - 包含所有必需的握手信号

**参考设计模式：**
{similar_designs}

**输出格式：**
返回JSON格式的架构定义：
```json
{{
  "version": 1,
  "hierarchy": {{
    "top": {{
      "name": "module_name",
      "type": "top",
      "description": "模块描述",
      "children": ["child1", "child2"],
      "ports": {{
        "clk": {{"type": "input", "width": 1, "description": "系统时钟"}},
        "rst_n": {{"type": "input", "width": 1, "description": "异步复位"}}
      }}
    }},
    "modules": [
      {{
        "name": "child1",
        "type": "leaf",
        "description": "子模块描述",
        "ports": {{}},
        "parameters": {{}}
      }}
    ]
  }},
  "interfaces": [
    {{
      "name": "s_axi",
      "protocol": "AXI4-Lite",
      "mode": "slave",
      "data_width": 32,
      "addr_width": 12
    }}
  ]
}}
```
"""
    
    def __init__(
        self,
        model_name: str = "gpt-4o",
        temperature: float = 0.2,
        api_key: Optional[str] = None,
        rag_persist_dir: str = "data/rag/vector_db",
        use_rag: bool = True,
    ):
        """Initialize Architect Agent.
        
        Args:
            model_name: OpenAI model name (use GPT-4 for complex architecture)
            temperature: LLM temperature
            api_key: OpenAI API key
            rag_persist_dir: RAG vector database directory
            use_rag: Whether to use RAG for design pattern retrieval
        """
        self.model_name = model_name
        self.temperature = temperature
        self.use_rag = use_rag
        
        # Initialize LLM
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
        )
        
        # Initialize RAG if enabled
        self.rag_loader = None
        if use_rag:
            try:
                self.rag_loader = KnowledgeLoader(persist_dir=rag_persist_dir)
                doc_count = self.rag_loader.vector_store.count()
                print(f"RAG initialized with {doc_count} documents")
            except Exception as e:
                print(f"Warning: RAG initialization failed: {e}")
                self.use_rag = False
    
    def design(
        self,
        intent: Dict[str, Any],
        constraints: Dict[str, List[Dict[str, Any]]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate architecture from design intent.
        
        Args:
            intent: Design intent (summary, interfaces, clock, reset)
            constraints: Hard/soft constraints
            metadata: Optional request metadata
        
        Returns:
            Architecture dictionary with hierarchy and interfaces
        """
        # Step 1: RAG retrieval for similar designs
        similar_designs = ""
        if self.use_rag and self.rag_loader:
            similar_designs = self._retrieve_similar_designs(intent, constraints)
        
        # Step 2: Construct prompt
        prompt = self._build_prompt(intent, constraints, similar_designs)
        
        # Step 3: Call LLM
        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT.format(
                similar_designs=similar_designs or "（无可用参考设计）"
            )),
            HumanMessage(content=prompt),
        ]
        
        response = self.llm.invoke(messages)
        
        # Step 4: Parse response
        try:
            architecture = self._parse_llm_response(response.content)
        except Exception as e:
            print(f"Warning: Architecture parsing failed: {e}")
            architecture = self._fallback_architecture(intent)
        
        # Step 5: Add metadata
        architecture["generated_at"] = datetime.now(timezone.utc).isoformat()
        architecture["model"] = self.model_name
        
        return architecture
    
    def _retrieve_similar_designs(
        self,
        intent: Dict[str, Any],
        constraints: Dict[str, List[Dict[str, Any]]],
    ) -> str:
        """Retrieve similar design patterns from RAG.
        
        Args:
            intent: Design intent
            constraints: Constraints
        
        Returns:
            Formatted string of similar designs
        """
        if not self.rag_loader:
            return ""
        
        # Build query
        query = intent.get("summary", "")
        interfaces = intent.get("interfaces", [])
        
        # Add interface keywords to query
        if interfaces:
            query += f" 接口: {', '.join(interfaces)}"
        
        # Search with filters
        filters = {}
        if interfaces:
            # Filter by interface tags
            filters["tags"] = {"$in": interfaces}
        
        try:
            results = self.rag_loader.search(query, n_results=3, filters=filters)
        except Exception as e:
            print(f"Warning: RAG search failed: {e}")
            return ""
        
        # Format results
        formatted = []
        for i, result in enumerate(results, 1):
            metadata = result.get("metadata", {})
            title = metadata.get("title", result["id"])
            score = result.get("score", 0)
            
            formatted.append(
                f"**参考设计 {i}**: {title} (相似度: {score:.2f})\n"
                f"{result['document'][:500]}...\n"
            )
        
        return "\n".join(formatted)
    
    def _build_prompt(
        self,
        intent: Dict[str, Any],
        constraints: Dict[str, List[Dict[str, Any]]],
        similar_designs: str,
    ) -> str:
        """Build prompt for architecture generation.
        
        Args:
            intent: Design intent
            constraints: Constraints
            similar_designs: Retrieved similar designs
        
        Returns:
            Formatted prompt
        """
        # Format constraints
        hard_constraints_str = "\n".join(
            f"  - {c['name']}: {c['value']}"
            for c in constraints.get("hard", [])
        )
        soft_constraints_str = "\n".join(
            f"  - {c['name']}: {c['value']}"
            for c in constraints.get("soft", [])
        )
        
        prompt = f"""请为以下需求设计模块架构：

**需求摘要**: {intent.get('summary', '')}

**目标HDL语言**: {intent.get('target_language', 'verilog')}

**时钟与复位**:
- 时钟: {intent.get('clock', 'clk')}
- 复位: {intent.get('reset', 'rst_n')}

**接口协议**: {', '.join(intent.get('interfaces', [])) or '无'}

**硬约束**:
{hard_constraints_str or '  无'}

**软约束（优化目标）**:
{soft_constraints_str or '  无'}

请生成完整的模块层次结构、端口定义和接口规范（JSON格式）。
"""
        return prompt
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM JSON response.
        
        Args:
            response: LLM response text
        
        Returns:
            Parsed architecture dictionary
        """
        # Extract JSON
        response = response.strip()
        
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            response = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            response = response[start:end].strip()
        
        architecture = json.loads(response)
        
        # Validate structure
        if "hierarchy" not in architecture:
            raise ValueError("Missing 'hierarchy' field in architecture")
        
        # Set defaults
        architecture.setdefault("version", 1)
        architecture.setdefault("interfaces", [])
        
        return architecture
    
    def _fallback_architecture(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Generate fallback architecture when LLM fails.
        
        Args:
            intent: Design intent
        
        Returns:
            Basic architecture structure
        """
        summary = intent.get("summary", "design")
        module_name = summary.lower().replace(" ", "_")[:30]
        
        return {
            "version": 1,
            "hierarchy": {
                "top": {
                    "name": module_name,
                    "type": "top",
                    "description": summary,
                    "children": [],
                    "ports": {
                        "clk": {"type": "input", "width": 1, "description": "系统时钟"},
                        "rst_n": {"type": "input", "width": 1, "description": "异步复位"},
                    }
                },
                "modules": []
            },
            "interfaces": []
        }


# LangGraph node function
def architecture_design_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node function for architecture design.
    
    Args:
        state: Current workflow state (expects 'intent' and 'constraints')
    
    Returns:
        Updated state with 'architecture' field
    """
    architect = ArchitectAgent()
    
    intent = state.get("intent", {})
    constraints = state.get("constraints", {"hard": [], "soft": []})
    metadata = state.get("metadata", {})
    
    architecture = architect.design(intent, constraints, metadata)
    
    # Initialize version tracking
    version_entry = {
        "version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "changes": "初始架构设计",
        "ppa_snapshot": None,
        "coverage_snapshot": None,
        "status": "baseline",
    }
    
    return {
        "architecture": architecture,
        "versions": [version_entry],
    }
