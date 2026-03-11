"""Unit tests for generator prompt template integration.

These tests validate that CodegenAgent uses Jinja2 templates instead of
hardcoded prompts during normal generation flow.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.generate_agent.codegen_agent import CodegenAgent
from app.prompts.loader import PromptLoader


class _FakeResponse:
    """Simple response container for fake LLM invocations."""

    def __init__(self, content: str):
        self.content = content


class _CapturingLLM:
    """Fake LLM that captures messages and returns deterministic output."""

    def __init__(self, content: str):
        self._content = content
        self.messages: List[Any] = []

    def invoke(self, messages: List[Any]) -> _FakeResponse:
        """Capture incoming messages and return fixed response."""
        self.messages = messages
        return _FakeResponse(self._content)


class _TracingPromptLoader(PromptLoader):
    """PromptLoader variant that records rendered template metadata."""

    def __init__(self):
        super().__init__()
        self.calls: List[Dict[str, Any]] = []

    def render(self, template_name: str, **context: Any) -> str:
        """Record template render call and return rendered text."""
        self.calls.append({"template": template_name, "context": context})
        return super().render(template_name, **context)


def _sample_state() -> Dict[str, Any]:
    """Build a minimal but representative codegen state payload."""
    return {
        "intent": {
            "summary": "设计一个最简单的8位乘法器。",
            "target_language": "verilog",
            "clock": "clk",
            "reset": "rst_n",
            "interfaces": [],
        },
        "constraints": {"hard": [], "soft": []},
        "architecture": {
            "hierarchy": {
                "top": {
                    "name": "mul8_top",
                    "type": "top",
                    "description": "8-bit multiplier top",
                    "children": [],
                    "ports": {},
                },
                "modules": [],
            },
            "interfaces": [],
        },
        "ppa": {},
        "metadata": {"source": "unit-test"},
    }


def test_render_codegen_template() -> None:
    """Generator template should render requirement and module guidance."""
    loader = PromptLoader()
    state = _sample_state()

    prompt = loader.render(
        "generator/hdl_generation.j2",
        payload=state,
        summary=state["intent"]["summary"],
        target_language=state["intent"]["target_language"],
        clock=state["intent"]["clock"],
        reset=state["intent"]["reset"],
        interfaces=state["intent"]["interfaces"],
        top_module=state["architecture"]["hierarchy"]["top"]["name"],
        constraints=state["constraints"],
        architecture=state["architecture"],
        ppa=state["ppa"],
    )

    assert "Verilog" in prompt
    assert "mul8_top" in prompt
    assert "TODO" in prompt


def test_codegen_agent_uses_template_prompt() -> None:
    """CodegenAgent should render generator template before LLM invocation."""
    fake_llm = _CapturingLLM(
        "module mul8_top (\n"
        "    input wire clk,\n"
        "    input wire rst_n\n"
        ");\n\n"
        "    // TODO: Interface signal declarations\n"
        "    // TODO: Register definitions\n"
        "    // TODO: Write path logic\n"
        "    // TODO: Read path logic\n"
        "endmodule\n"
    )
    tracing_loader = _TracingPromptLoader()

    agent = CodegenAgent(llm=fake_llm, prompt_loader=tracing_loader)
    result = agent.generate_framework(_sample_state())

    assert tracing_loader.calls[0]["template"] == "generator/hdl_generation.j2"
    assert "8位乘法器" in fake_llm.messages[0].content
    assert "\"intent\"" in fake_llm.messages[1].content
    assert "module mul8_top" in result["generated_code"]["content"]