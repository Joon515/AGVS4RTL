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

from ..llm_config import resolve_agent_llm_config
from ..prompts.loader import PromptLoader
from ..rag.vector_store import KnowledgeLoader


class ArchitectAgent:
    """RAG-enhanced architecture design agent."""
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        rag_persist_dir: str = "data/rag/vector_db",
        use_rag: bool = True,
        llm: Optional[Any] = None,
        prompt_loader: Optional[PromptLoader] = None,
    ):
        """Initialize Architect Agent.
        
        Args:
            model_name: OpenAI model name (use GPT-4 for complex architecture)
            temperature: LLM temperature
            api_key: OpenAI API key
            rag_persist_dir: RAG vector database directory
            use_rag: Whether to use RAG for design pattern retrieval
            llm: Optional injected LLM-compatible client for testing
            prompt_loader: Optional injected prompt loader
        """
        cfg = resolve_agent_llm_config(
            "architecture_agent",
            model_name=model_name,
            temperature=temperature,
            api_key=api_key,
            api_base=api_base,
        )

        self.model_name = cfg["model_name"] or "deepseek-reasoner"
        self.temperature = cfg["temperature"] if cfg["temperature"] is not None else 0.2
        self.use_rag = use_rag
        debug = cfg.get("_debug", {})
        print(
            f"[ArchitectAgent] Init: model={self.model_name}, "
            f"api_base={cfg['api_base']}, "
            f"has_key={debug.get('has_api_key')}, "
            f"key_src={debug.get('api_key_source')}"
        )
        
        # Initialize LLM
        self.llm = llm or ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            openai_api_key=cfg["api_key"],
            openai_api_base=cfg["api_base"],
        )
        self.prompt_loader = prompt_loader or PromptLoader()
        
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
        system_prompt = self.prompt_loader.render(
            "architect/design_proposal.j2",
            similar_designs=similar_designs,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ]
        
        try:
            print(f"[ArchitectAgent] Calling LLM: model={self.model_name}")
            response = self.llm.invoke(messages)
            raw_content = str(getattr(response, "content", ""))
            print(f"[ArchitectAgent] LLM response length: {len(raw_content)} chars")
            architecture = self._parse_llm_response(raw_content)
        except Exception as e:
            print(f"[ArchitectAgent] Architecture LLM/parsing failed: {type(e).__name__}: {e}")
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
        
        return self.prompt_loader.render(
            "architect/module_decomposition.j2",
            context=(
                "请为以下需求设计模块架构：\n\n"
                f"**需求摘要**: {intent.get('summary', '')}\n\n"
                f"**目标HDL语言**: {intent.get('target_language', 'verilog')}\n\n"
                "**时钟与复位**:\n"
                f"- 时钟: {intent.get('clock', 'clk')}\n"
                f"- 复位: {intent.get('reset', 'rst_n')}\n\n"
                f"**接口协议**: {', '.join(intent.get('interfaces', [])) or '无'}\n\n"
                "**硬约束**:\n"
                f"{hard_constraints_str or '  无'}\n\n"
                "**软约束（优化目标）**:\n"
                f"{soft_constraints_str or '  无'}\n\n"
                "请生成完整的模块层次结构、端口定义和接口规范（JSON格式）。"
            ),
        )
    
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
    
    @staticmethod
    def _safe_module_name(raw: str) -> str:
        """Sanitize raw text into a valid Verilog module name."""
        import re
        name = raw.lower().strip()
        name = re.sub(r"[^a-z0-9_]+", "_", name)
        name = re.sub(r"_+", "_", name).strip("_")
        if not name:
            name = "top_module"
        if not name[0].isalpha() and name[0] != "_":
            name = f"m_{name}"
        return name[:64]

    def _fallback_architecture(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Generate fallback architecture when LLM fails.
        
        Args:
            intent: Design intent
        
        Returns:
            Basic architecture structure
        """
        summary = intent.get("summary", "design")
        module_name = self._safe_module_name(summary)
        
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

    round_outputs = list(state.get("round_outputs", []))
    round_outputs.append(
        {
            "round": len(round_outputs) + 1,
            "stage": "architect",
            "model": architect.model_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_snapshot": {
                "intent": intent,
                "constraints": constraints,
                "metadata": metadata,
            },
            "output": {
                "architecture": architecture,
            },
        }
    )
    
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
        "round_outputs": round_outputs,
    }
