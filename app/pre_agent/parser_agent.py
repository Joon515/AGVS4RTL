"""Parser Agent for natural language requirement extraction.

This agent processes natural language input and extracts structured design intent
and constraints. It uses LLM to understand HDL-specific terminology and requirements.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..llm_config import resolve_agent_llm_config
from ..pre_agent.stracture_request import (
    Constraint,
    DesignIntent,
    NaturalLanguageRequest,
    PreprocessOutput,
    StructuredConstraints,
)


class ParserAgent:
    """LLM-powered parser for HDL requirement extraction."""
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ):
        """Initialize Parser Agent.
        
        Args:
            model_name: OpenAI model name
            temperature: LLM temperature (lower = more deterministic)
            api_key: OpenAI API key (or use OPENAI_API_KEY env var)
            llm: Optional injected LLM-compatible client for testing
            prompt_loader: Optional injected prompt loader
        """
        cfg = resolve_agent_llm_config(
            "pre_agent",
            model_name=model_name,
            temperature=temperature,
            api_key=api_key,
            api_base=api_base,
        )

        self.model_name = cfg["model_name"] or "deepseek-chat"
        self.temperature = cfg["temperature"] if cfg["temperature"] is not None else 0.1
        
        # Initialize LLM
        self.llm = ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            openai_api_key=cfg["api_key"],
            openai_api_base=cfg["api_base"],
        )
        self.prompt_loader = prompt_loader or PromptLoader()
    
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
        # Construct prompt from template
        system_prompt = self.prompt_loader.render(
            "parser/extract_intent.j2",
            requirement=natural_language,
            target_language="verilog",
            examples=self._get_few_shot_examples(),
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"请分析以下需求：\n\n{natural_language}"),
        ]
        
        try:
            response = self.llm.invoke(messages)
            parsed = self._parse_llm_response(response.content)
        except Exception as e:
            print(f"Warning: LLM parsing failed, using fallback. Error: {e}")
            parsed = self._fallback_parse(natural_language)
        
        # Create PreprocessOutput
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

    def _get_few_shot_examples(self) -> List[Dict[str, Any]]:
        """Return built-in few-shot examples for parser prompt.

        Returns:
            Few-shot examples that reinforce output structure.
        """
        return [
            {
                "description": "AXI-Lite 寄存器文件",
                "requirement": "实现一个带AXI-Lite接口的寄存器文件",
                "result": {
                    "intent": {
                        "summary": "实现一个带AXI-Lite接口的寄存器文件",
                        "target_language": "verilog",
                        "clock": "clk",
                        "reset": "rst_n",
                        "interfaces": ["axi-lite"],
                    },
                    "constraints": {
                        "hard": [],
                        "soft": [{"name": "area", "value": "minimize"}],
                    },
                },
            }
        ]
    
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

    # Multi-round output trace
    round_outputs = list(state.get("round_outputs", []))
    round_outputs.append(
        {
            "round": len(round_outputs) + 1,
            "stage": "parser",
            "model": parser.model_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_snapshot": {
                "natural_language": natural_language,
                "language": language,
                "source": source,
            },
            "output": {
                "intent": result.get("intent", {}),
                "constraints": result.get("constraints", {}),
            },
        }
    )
    
    # Return state update
    return {
        "natural_language": natural_language,
        "language": language,
        "source": source,
        **result,
        "round_outputs": round_outputs,
    }
