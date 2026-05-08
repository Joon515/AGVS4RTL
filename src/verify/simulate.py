"""
Cocotb testbench generation for Verify module.

Generates testbench .py files and Makefiles from SpecReg verification fields.
Uses LLM-driven generation when available; rule-based fallback for Makefile.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import json

from src.common.models import SpecReg, LlmRuntimeConfig
from src.common.llm_utils import _call_openai_compatible_chat


def generate_cocotb_makefile(
    spec_reg: SpecReg,
    output_dir: str,
    rtl_paths: List[str],
) -> str:
    """
    Generate a standard cocotb Makefile.

    Returns the path to the generated Makefile.
    """
    top_module = spec_reg.top_module
    verilog_sources = " ".join(rtl_paths)

    makefile_content = f"""# Cocotb Makefile - Auto-generated for {top_module}
TOPLEVEL_LANG=verilog
VERILOG_SOURCES={verilog_sources}
TOPLEVEL={top_module}
MODULE=test_{top_module}
SIM=icarus
"""

    makefile_path = Path(output_dir) / "Makefile"
    makefile_path.write_text(makefile_content, encoding="utf-8")
    return str(makefile_path)


def _build_testbench_prompt(spec_reg: SpecReg) -> str:
    """Build LLM prompt for testbench generation from SpecReg fields."""
    clock_info = ""
    if spec_reg.has_clock_reset_definition():
        cr = spec_reg.clock_and_reset[0]
        clock_info = (
            f"Clock: {cr.clock_name}, Reset: {cr.reset_name} (type: {cr.reset_type.value})\n"
        )

    directives = "\n".join(f"- {d}" for d in spec_reg.verification_directives) or "(none)"
    requirements = "\n".join(f"- {r}" for r in spec_reg.functional_requirements) or "(none)"
    corners = "\n".join(f"- {c}" for c in spec_reg.corner_cases) or "(none)"
    illegals = "\n".join(f"- {i}" for i in spec_reg.illegal_conditions) or "(none)"

    prompt = f"""Generate a complete cocotb Python testbench for the following Verilog module.

Module name: {spec_reg.top_module}
Module description: {spec_reg.module_description}
{clock_info}
Ports:
{json.dumps([p.model_dump(mode='json') for p in spec_reg.ports], indent=2)}

Verification directives:
{directives}

Functional requirements:
{requirements}

Corner cases:
{corners}

Illegal conditions:
{illegals}

Generate ONLY valid Python code compatible with cocotb 2.x. No explanations, no markdown fences.
The testbench must:
1. Import cocotb and required modules correctly
2. Define a clock coroutine (use Clock from cocotb.triggers)
3. Include reset sequence matching '{spec_reg.clock_and_reset[0].reset_type.value if spec_reg.has_clock_reset_definition() else 'sync_high'}'
4. Implement test cases covering the functional requirements above
5. Include assertions/checks for corner cases and illegal conditions
6. Use @cocotb.test() decorator for each test case

Do NOT include markdown fences (```) in the output. Return ONLY the Python code.
"""
    return prompt


def generate_cocotb_testbench(
    spec_reg: SpecReg,
    output_dir: str,
    llm_config: Optional[LlmRuntimeConfig] = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Generate cocotb testbench Python file using LLM.

    Args:
        spec_reg: SpecReg contract with verification fields
        output_dir: Directory to write testbench file
        llm_config: LLM runtime config; if None or disabled, raises ValueError

    Returns:
        (testbench_path, llm_transcript) tuple

    Raises:
        ValueError: If LLM is not available
    """
    if llm_config is None or not llm_config.enabled:
        raise ValueError(
            "LLM is required for testbench generation. "
            "Set llm_config.enabled=True and provide valid API credentials."
        )

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert cocotb verification engineer. "
                "Generate complete, correct cocotb 2.x Python testbenches. "
                "Always use proper cocotb imports and decorators. "
                "Return ONLY Python code, no explanations."
            ),
        },
        {
            "role": "user",
            "content": _build_testbench_prompt(spec_reg),
        },
    ]

    content, transcript = _call_openai_compatible_chat(llm_config, messages)

    # Strip any remaining markdown fences
    content = content.strip()
    if content.startswith("```python"):
        content = content[9:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    testbench_path = Path(output_dir) / f"test_{spec_reg.top_module}.py"
    testbench_path.write_text(content, encoding="utf-8")

    transcript.update({
        "stage": "testbench",
        "profile": llm_config.profile,
    })

    return str(testbench_path), transcript
