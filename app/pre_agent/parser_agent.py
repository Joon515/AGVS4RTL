"""Parser Agent for natural language requirement extraction.

This agent processes natural language input and extracts structured design intent
and constraints. It uses LLM to understand HDL-specific terminology and requirements.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..pre_agent.stracture_request import (
    Constraint,
    DesignIntent,
    PreprocessOutput,
    StructuredConstraints,
)


class ParserAgent:
    """LLM-powered parser for HDL requirement extraction."""
    
    # System prompt for requirement parsing
    SYSTEM_PROMPT = """你是一个专业的硬件设计需求分析专家。你的任务是从自然语言需求中提取结构化的设计意图和约束条件。

**分析要点:**
1. **设计意图 (Design Intent)**:
   - 核心功能摘要
   - 目标HDL语言 (Verilog/SystemVerilog/VHDL)
   - 时钟信号名称
   - 复位信号名称（注意低电平有效 rst_n vs 高电平有效 rst）
   - 接口协议关键词 (AXI, APB, AXI-Stream, UART, SPI等)

2. **约束条件 (Constraints)**:
   - **硬约束 (Hard)**: 必须满足的要求（频率、数据位宽、地址位宽等）
   - **软约束 (Soft)**: 优化目标（面积最小化、功耗最小化等）

**输出格式:**
返回 JSON 格式，包含以下字段：
```json
{
  "intent": {
    "summary": "功能摘要",
    "target_language": "verilog",
    "clock": "clk",
    "reset": "rst_n",
    "interfaces": ["axi-lite", "apb"]
  },
  "constraints": {
    "hard": [
      {"name": "freq", "value": "200MHz"},
      {"name": "data_width", "value": 32}
    ],
    "soft": [
      {"name": "area", "value": "minimize"},
      {"name": "power", "value": "low"}
    ]
  }
}
```

**注意事项:**
- 如果用户未明确指定，使用合理默认值
- 频率单位统一为 MHz
- 数据位宽统一为整数
- 接口名称使用标准协议名（小写，用连字符）
"""
    
    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.1,
        api_key: Optional[str] = None,
    ):
        """Initialize Parser Agent.
        
        Args:
            model_name: OpenAI model name
            temperature: LLM temperature (lower = more deterministic)
            api_key: OpenAI API key (or use OPENAI_API_KEY env var)
        """
        self.model_name = model_name
        self.temperature = temperature
        
        # Initialize LLM
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
        )
    
    def parse(
        self,
        natural_language: str,
        language: str = "zh",
        source: str = "tui",
    ) -> PreprocessOutput:
        """Parse natural language requirement into structured output.
        
        Args:
            natural_language: User's requirement text
            language: Input language ("zh" or "en")
            source: Input source ("tui" or "api")
        
        Returns:
            PreprocessOutput with structured intent and constraints
        """
        # Construct prompt
        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(content=f"请分析以下需求：\n\n{natural_language}"),
        ]
        
        # Call LLM
        response = self.llm.invoke(messages)
        
        # Parse LLM response
        try:
            parsed = self._parse_llm_response(response.content)
        except Exception as e:
            print(f"Warning: LLM parsing failed, using fallback. Error: {e}")
            parsed = self._fallback_parse(natural_language)
        
        # Create PreprocessOutput
        from ..pre_agent.stracture_request import (
            NaturalLanguageRequest,
            Preprocessor,
        )
        
        raw = NaturalLanguageRequest(
            text=natural_language,
            language=language,
            source=source,
        )
        
        from datetime import datetime, timezone
        from uuid import uuid4
        
        output = PreprocessOutput(
            request_id=str(uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            intent=DesignIntent(**parsed["intent"]),
            constraints=StructuredConstraints(
                hard=[Constraint(**c) for c in parsed["constraints"]["hard"]],
                soft=[Constraint(**c) for c in parsed["constraints"]["soft"]],
            ),
            raw=raw,
        )
        
        return output
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM JSON response.
        
        Args:
            response: LLM response text
        
        Returns:
            Parsed dictionary
        """
        # Try to extract JSON from response
        # LLM might wrap JSON in ```json ... ```
        response = response.strip()
        
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            response = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            response = response[start:end].strip()
        
        parsed = json.loads(response)
        
        # Validate structure
        if "intent" not in parsed or "constraints" not in parsed:
            raise ValueError("Missing required fields: intent or constraints")
        
        # Set defaults
        intent = parsed["intent"]
        intent.setdefault("target_language", "verilog")
        intent.setdefault("clock", "clk")
        intent.setdefault("reset", "rst_n")
        intent.setdefault("interfaces", [])
        
        constraints = parsed["constraints"]
        constraints.setdefault("hard", [])
        constraints.setdefault("soft", [])
        
        # Add priority field if missing
        for c in constraints["hard"]:
            c.setdefault("priority", 0)
        for c in constraints["soft"]:
            c.setdefault("priority", 1)
        
        return parsed
    
    def _fallback_parse(self, text: str) -> Dict[str, Any]:
        """Fallback parser when LLM fails.
        
        Args:
            text: Natural language text
        
        Returns:
            Basic parsed structure
        """
        # Simple keyword-based extraction
        interfaces = []
        if "axi" in text.lower():
            if "lite" in text.lower():
                interfaces.append("axi-lite")
            elif "stream" in text.lower():
                interfaces.append("axi-stream")
            else:
                interfaces.append("axi")
        if "apb" in text.lower():
            interfaces.append("apb")
        if "uart" in text.lower():
            interfaces.append("uart")
        if "spi" in text.lower():
            interfaces.append("spi")
        
        # Extract frequency if present
        hard_constraints = []
        import re
        freq_match = re.search(r"(\d+)\s*(mhz|MHz)", text)
        if freq_match:
            hard_constraints.append({
                "name": "freq",
                "value": f"{freq_match.group(1)}MHz",
                "priority": 0,
            })
        
        # Extract data width
        width_match = re.search(r"(\d+)\s*bit", text, re.IGNORECASE)
        if width_match:
            hard_constraints.append({
                "name": "data_width",
                "value": int(width_match.group(1)),
                "priority": 0,
            })
        
        return {
            "intent": {
                "summary": text.strip(),
                "target_language": "verilog",
                "clock": "clk",
                "reset": "rst_n",
                "interfaces": interfaces,
            },
            "constraints": {
                "hard": hard_constraints,
                "soft": [],
            },
        }
    
    def parse_to_state(
        self,
        natural_language: str,
        language: str = "zh",
        source: str = "tui",
    ) -> Dict[str, Any]:
        """Parse and convert to LangGraph state format.
        
        Args:
            natural_language: User's requirement text
            language: Input language
            source: Input source
        
        Returns:
            Partial state dict ready for LangGraph
        """
        output = self.parse(natural_language, language, source)
        return output.to_state()


# LangGraph node function
def parse_requirement_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node function for requirement parsing.
    
    Args:
        state: Current workflow state (expects 'natural_language' field)
    
    Returns:
        Updated state with intent, constraints, metadata
    """
    parser = ParserAgent()
    
    # Get input from state
    natural_language = state.get("natural_language", "")
    language = state.get("language", "zh")
    source = state.get("source", "tui")
    
    # Parse
    result = parser.parse_to_state(natural_language, language, source)
    
    # Return state update
    return result
