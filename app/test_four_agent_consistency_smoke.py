#!/usr/bin/env python3
"""Four-agent consistency smoke test.

Rules:
1) Upstream output and downstream input must be exact passthrough.
2) NLP semantics and intent/constraints JSON semantics must be highly aligned.
3) Requirement functionality and generated code framework must be highly aligned.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.workflow import run_full_codegen_workflow


DEFAULT_CASES = [
    "设计一个最简单的8位乘法器。",
    "设计一个最简单的8位有符号乘法器。",
    "实现一个最简单的8位组合逻辑乘法器模块。",
]


def _extract_keywords(text: str) -> Dict[str, Any]:
    lower = text.lower()
    interfaces: List[str] = []
    if "axi" in lower:
        interfaces.append("axi-lite" if "lite" in lower else "axi")
    if "apb" in lower:
        interfaces.append("apb")
    if "uart" in lower:
        interfaces.append("uart")
    if "spi" in lower:
        interfaces.append("spi")

    freq_matches = re.findall(r"(\d+)\s*mhz", lower)
    width_matches = re.findall(r"(\d+)\s*(?:bit|位)", lower)

    return {
        "interfaces": interfaces,
        "freqs": [int(x) for x in freq_matches],
        "widths": [int(x) for x in width_matches],
    }


def _find_stage(round_outputs: List[Dict[str, Any]], stage: str) -> Dict[str, Any]:
    for item in round_outputs:
        if item.get("stage") == stage:
            return item
    return {}


def _check_passthrough(round_outputs: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    parser = _find_stage(round_outputs, "parser")
    architect = _find_stage(round_outputs, "architect")
    codegen = _find_stage(round_outputs, "codegen")
    verify = _find_stage(round_outputs, "verify")

    parser_out = parser.get("output", {})
    architect_in = architect.get("input_snapshot", {})
    codegen_in = codegen.get("input_snapshot", {})
    architect_out = architect.get("output", {})
    codegen_out = codegen.get("output", {})
    verify_in = verify.get("input_snapshot", {})

    if architect_in.get("intent") != parser_out.get("intent"):
        errors.append("architect.input.intent != parser.output.intent")
    if architect_in.get("constraints") != parser_out.get("constraints"):
        errors.append("architect.input.constraints != parser.output.constraints")

    if codegen_in.get("intent") != parser_out.get("intent"):
        errors.append("codegen.input.intent != parser.output.intent")
    if codegen_in.get("constraints") != parser_out.get("constraints"):
        errors.append("codegen.input.constraints != parser.output.constraints")
    if codegen_in.get("architecture") != architect_out.get("architecture"):
        errors.append("codegen.input.architecture != architect.output.architecture")

    if verify_in.get("intent") != parser_out.get("intent"):
        errors.append("verify.input.intent != parser.output.intent")
    if verify_in.get("constraints") != parser_out.get("constraints"):
        errors.append("verify.input.constraints != parser.output.constraints")
    if verify_in.get("architecture") != architect_out.get("architecture"):
        errors.append("verify.input.architecture != architect.output.architecture")
    if verify_in.get("generated_code") != codegen_out.get("generated_code"):
        errors.append("verify.input.generated_code != codegen.output.generated_code")

    return (len(errors) == 0, errors)


def _check_nlp_json_alignment(requirement: str, result: Dict[str, Any]) -> Tuple[bool, int, List[str]]:
    issues: List[str] = []
    intent = result.get("intent", {})
    constraints = result.get("constraints", {})
    summary = str(intent.get("summary", "")).strip()
    kws = _extract_keywords(requirement)

    score = 100
    if not summary:
        score -= 35
        issues.append("intent.summary missing")

    interfaces = [str(x).lower() for x in intent.get("interfaces", [])]
    for itf in kws["interfaces"]:
        if not any(itf in x or x in itf for x in interfaces):
            score -= 15
            issues.append(f"interface missing in intent: {itf}")

    hard = constraints.get("hard", [])
    hard_text = " ".join(str(item) for item in hard).lower()
    for freq in kws["freqs"]:
        if str(freq) not in hard_text:
            score -= 10
            issues.append(f"freq missing in constraints: {freq}MHz")
    for width in kws["widths"]:
        if str(width) not in hard_text:
            score -= 10
            issues.append(f"width missing in constraints: {width}")

    score = max(0, min(100, score))
    return (score >= 80, score, issues)


def _check_requirement_code_alignment(requirement: str, result: Dict[str, Any]) -> Tuple[bool, int, List[str]]:
    issues: List[str] = []
    generated_code = result.get("generated_code", {})
    code = str(generated_code.get("content", ""))
    verify = result.get("verification", {})
    kws = _extract_keywords(requirement)

    score = 100
    if "module" not in code:
        score -= 40
        issues.append("module keyword missing")

    lower_code = code.lower()
    for itf in kws["interfaces"]:
        if "axi" in itf and "axi_" not in lower_code:
            score -= 20
            issues.append("AXI interface signals not found")
        if "apb" in itf and "apb_" not in lower_code:
            score -= 20
            issues.append("APB interface signals not found")
        if "uart" in itf and "uart" not in lower_code:
            score -= 20
            issues.append("UART related signals not found")

    verify_score = verify.get("consistency_score")
    if isinstance(verify_score, (int, float)):
        if verify_score < 70:
            score -= 20
            issues.append(f"verify consistency_score too low: {verify_score}")
    else:
        score -= 10
        issues.append("verification consistency_score missing")

    score = max(0, min(100, score))
    return (score >= 80, score, issues)


def run_case(requirement: str) -> Dict[str, Any]:
    result = run_full_codegen_workflow(requirement, language="zh", source="smoke-consistency")
    round_outputs = list(result.get("round_outputs", []))

    pass_through_ok, pass_through_issues = _check_passthrough(round_outputs)
    nlp_json_ok, nlp_json_score, nlp_json_issues = _check_nlp_json_alignment(requirement, result)
    req_code_ok, req_code_score, req_code_issues = _check_requirement_code_alignment(requirement, result)

    return {
        "requirement": requirement,
        "models": {
            "parser": _find_stage(round_outputs, "parser").get("model"),
            "architect": _find_stage(round_outputs, "architect").get("model"),
            "codegen": _find_stage(round_outputs, "codegen").get("model"),
            "verify": _find_stage(round_outputs, "verify").get("model"),
        },
        "checks": {
            "passthrough_exact": {
                "pass": pass_through_ok,
                "issues": pass_through_issues,
            },
            "nlp_json_high_alignment": {
                "pass": nlp_json_ok,
                "score": nlp_json_score,
                "issues": nlp_json_issues,
            },
            "requirement_code_high_alignment": {
                "pass": req_code_ok,
                "score": req_code_score,
                "issues": req_code_issues,
            },
        },
        "round_count": len(round_outputs),
        "verification": result.get("verification", {}),
    }


def run_case_from_result(requirement: str, result: Dict[str, Any]) -> Dict[str, Any]:
    round_outputs = list(result.get("round_outputs", []))

    pass_through_ok, pass_through_issues = _check_passthrough(round_outputs)
    nlp_json_ok, nlp_json_score, nlp_json_issues = _check_nlp_json_alignment(requirement, result)
    req_code_ok, req_code_score, req_code_issues = _check_requirement_code_alignment(requirement, result)

    return {
        "requirement": requirement,
        "models": {
            "parser": _find_stage(round_outputs, "parser").get("model"),
            "architect": _find_stage(round_outputs, "architect").get("model"),
            "codegen": _find_stage(round_outputs, "codegen").get("model"),
            "verify": _find_stage(round_outputs, "verify").get("model"),
        },
        "checks": {
            "passthrough_exact": {
                "pass": pass_through_ok,
                "issues": pass_through_issues,
            },
            "nlp_json_high_alignment": {
                "pass": nlp_json_ok,
                "score": nlp_json_score,
                "issues": nlp_json_issues,
            },
            "requirement_code_high_alignment": {
                "pass": req_code_ok,
                "score": req_code_score,
                "issues": req_code_issues,
            },
        },
        "round_count": len(round_outputs),
        "verification": result.get("verification", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="4-agent consistency smoke test")
    parser.add_argument("--case", action="append", help="Requirement text (repeatable)")
    parser.add_argument(
        "--result-json",
        default=None,
        help="Existing workflow result JSON path for offline consistency check",
    )
    parser.add_argument(
        "--output",
        default="/app/data/workspace/test_output/four_agent_consistency_smoke.json",
        help="Output JSON report path",
    )
    args = parser.parse_args()

    cases = args.case if args.case else DEFAULT_CASES

    if args.result_json:
        loaded = json.loads(Path(args.result_json).read_text(encoding="utf-8"))
        requirement = (args.case[0] if args.case else "") or loaded.get("natural_language") or loaded.get("intent", {}).get("summary", "")
        item = run_case_from_result(requirement, loaded)
        report_items = [item]
    else:
        report_items: List[Dict[str, Any]] = []
        for idx, requirement in enumerate(cases, 1):
            print(f"[case {idx}] {requirement}")
            try:
                item = run_case(requirement)
            except Exception as exc:
                item = {
                    "requirement": requirement,
                    "error": str(exc),
                    "checks": {
                        "passthrough_exact": {"pass": False, "issues": ["workflow execution failed"]},
                        "nlp_json_high_alignment": {"pass": False, "score": 0, "issues": ["workflow execution failed"]},
                        "requirement_code_high_alignment": {"pass": False, "score": 0, "issues": ["workflow execution failed"]},
                    },
                }
            report_items.append(item)

    overall_pass = all(
        item.get("checks", {}).get("passthrough_exact", {}).get("pass")
        and item.get("checks", {}).get("nlp_json_high_alignment", {}).get("pass")
        and item.get("checks", {}).get("requirement_code_high_alignment", {}).get("pass")
        for item in report_items
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_pass": overall_pass,
        "rules": [
            "upstream_output_downstream_input_exact_passthrough",
            "nlp_semantics_json_semantics_high_alignment",
            "requirement_functionality_code_framework_high_alignment",
        ],
        "cases": report_items,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved={out_path}")
    print(f"overall_pass={overall_pass}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
