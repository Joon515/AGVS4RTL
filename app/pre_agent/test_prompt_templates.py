"""Unit tests for Jinja2 prompt template refactor.

These tests validate that prompt templates are rendered correctly and
integrated into ParserAgent and ArchitectAgent without requiring real API calls.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.manage_agent.architect_agent import ArchitectAgent
from app.pre_agent.parser_agent import ParserAgent
from app.prompts.loader import PromptLoader


class _FakeResponse:
    """Simple response container for fake LLM invocations."""

    def __init__(self, content: str):
        self.content = content


class _CapturingLLM:
    """Fake LLM that captures the latest messages and returns fixed content."""

    def __init__(self, content: str):
        self._content = content
        self.messages: List[Any] = []

    def invoke(self, messages: List[Any]) -> _FakeResponse:
        """Capture incoming messages and return deterministic response."""
        self.messages = messages
        return _FakeResponse(self._content)


class _TracingPromptLoader(PromptLoader):
    """PromptLoader variant that records all rendered templates."""

    def __init__(self):
        super().__init__()
        self.calls: List[Dict[str, Any]] = []

    def render(self, template_name: str, **context: Any) -> str:
        """Record template render call and return rendered prompt."""
        self.calls.append({"template": template_name, "context": context})
        return super().render(template_name, **context)


def test_prompt_loader_initialization() -> None:
    """PromptLoader should initialize Jinja2 environment."""
    loader = PromptLoader()
    assert loader.env is not None


def test_render_parser_template() -> None:
    """Parser template should render requirement and target language."""
    loader = PromptLoader()

    prompt = loader.render(
        "parser/extract_intent.j2",
        requirement="实现一个UART发送器",
        target_language="verilog",
        examples=[],
    )

    assert "UART" in prompt
    assert "verilog" in prompt
    assert "intent" in prompt
    assert "constraints" in prompt


def test_json_format_filter() -> None:
    """json_format filter should output readable JSON text."""
    loader = PromptLoader()
    template = loader.env.from_string("{{ data | json_format }}")
    output = template.render(data={"key": "值"})
    assert '"key": "值"' in output or '"key":"值"' in output


def test_parser_agent_uses_template_prompt() -> None:
    """ParserAgent should render parser template before LLM invocation."""
    fake_llm = _CapturingLLM(
        '{"intent": {"summary": "UART 接收器", "target_language": "verilog", '
        '"clock": "clk", "reset": "rst_n", "interfaces": ["uart"]}, '
        '"constraints": {"hard": [], "soft": []}}'
    )
    tracing_loader = _TracingPromptLoader()

    parser = ParserAgent(llm=fake_llm, prompt_loader=tracing_loader)
    result = parser.parse("实现一个UART接收器")

    assert result.intent.summary == "UART 接收器"
    assert result.intent.target_language == "verilog"
    assert tracing_loader.calls[0]["template"] == "parser/extract_intent.j2"
    assert "实现一个UART接收器" in fake_llm.messages[0].content


def test_architect_agent_uses_template_prompt() -> None:
    """ArchitectAgent should render architect templates during design flow."""
    fake_llm = _CapturingLLM(
        '{"version": 1, "hierarchy": {"top": {"name": "demo_top", "type": "top", '
        '"description": "demo", "children": [], "ports": {}}, "modules": []}, '
        '"interfaces": []}'
    )
    tracing_loader = _TracingPromptLoader()

    agent = ArchitectAgent(
        use_rag=False,
        llm=fake_llm,
        prompt_loader=tracing_loader,
    )

    architecture = agent.design(
        intent={
            "summary": "demo architecture",
            "target_language": "verilog",
            "clock": "clk",
            "reset": "rst_n",
            "interfaces": ["axi-lite"],
        },
        constraints={"hard": [], "soft": []},
    )

    rendered_templates = [call["template"] for call in tracing_loader.calls]
    assert "architect/design_proposal.j2" in rendered_templates
    assert "architect/module_decomposition.j2" in rendered_templates
    assert architecture["hierarchy"]["top"]["name"] == "demo_top"
