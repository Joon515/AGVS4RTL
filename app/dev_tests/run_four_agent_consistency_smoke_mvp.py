#!/usr/bin/env python3
"""4-agent consistency smoke test (MVP version).

MVP gating rules:
1) framework_minimal_valid: generated code contains module skeleton.
2) nlp_json_high_alignment: natural language semantics aligns with intent/constraints.
3) verify_score_gate: verification score reaches threshold.

Notes:
- Backend implementation completeness is intentionally NOT gated in MVP.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from ._bootstrap import ensure_project_root
except ImportError:
    from _bootstrap import ensure_project_root

PROJECT_ROOT = ensure_project_root()

from app.workflow import run_full_codegen_workflow


DEFAULT_CASES = [
    "设计一个最简单的8位乘法器。",
]


def _workspace_root() -> Path:
    """Resolve workspace root for local and container execution."""
    app_root = Path("/app")
    return app_root if app_root.exists() else PROJECT_ROOT


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


def _check_framework_minimal(result: Dict[str, Any]) -> Tuple[bool, int, List[str]]:
    issues: List[str] = []
    generated_code = result.get("generated_code", {})
    code = str(generated_code.get("content", "")).strip()

    score = 100
    if not code:
        score -= 60
        issues.append("generated_code.content empty")
    if "module" not in code:
        score -= 30
        issues.append("module keyword missing")
    if "endmodule" not in code:
        score -= 10
        issues.append("endmodule keyword missing")

    score = max(0, min(100, score))
    return (score >= 80, score, issues)


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


def _normalize_verify_score(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    score = float(value)
    if score <= 1.0:
        return score * 100.0
    return score


def _check_verify_score(result: Dict[str, Any], threshold: float) -> Tuple[bool, float, List[str]]:
    issues: List[str] = []
    verification = result.get("verification", {})
    normalized = _normalize_verify_score(verification.get("consistency_score"))
    if normalized is None:
        issues.append("verification consistency_score missing")
        return False, 0.0, issues

    passed = normalized >= threshold
    if not passed:
        issues.append(f"verify score below threshold: {normalized:.1f} < {threshold:.1f}")
    return passed, normalized, issues


def evaluate_case(requirement: str, result: Dict[str, Any], verify_threshold: float) -> Dict[str, Any]:
    round_outputs = list(result.get("round_outputs", []))

    framework_ok, framework_score, framework_issues = _check_framework_minimal(result)
    nlp_ok, nlp_score, nlp_issues = _check_nlp_json_alignment(requirement, result)
    verify_ok, verify_score, verify_issues = _check_verify_score(result, verify_threshold)

    return {
        "requirement": requirement,
        "models": {
            "parser": _find_stage(round_outputs, "parser").get("model"),
            "architect": _find_stage(round_outputs, "architect").get("model"),
            "codegen": _find_stage(round_outputs, "codegen").get("model"),
            "verify": _find_stage(round_outputs, "verify").get("model"),
        },
        "checks": {
            "framework_minimal_valid": {
                "pass": framework_ok,
                "score": framework_score,
                "issues": framework_issues,
            },
            "nlp_json_high_alignment": {
                "pass": nlp_ok,
                "score": nlp_score,
                "issues": nlp_issues,
            },
            "verify_score_gate": {
                "pass": verify_ok,
                "score": round(verify_score, 2),
                "threshold": verify_threshold,
                "issues": verify_issues,
            },
        },
        "round_count": len(round_outputs),
        "verification": result.get("verification", {}),
    }


def run_case_online(requirement: str, verify_threshold: float) -> Dict[str, Any]:
    result = run_full_codegen_workflow(requirement, language="zh", source="smoke-consistency-mvp")
    return evaluate_case(requirement, result, verify_threshold)


def run_case_offline(requirement: str, result_json: str, verify_threshold: float) -> Dict[str, Any]:
    loaded = json.loads(Path(result_json).read_text(encoding="utf-8"))
    req = requirement or loaded.get("natural_language") or loaded.get("intent", {}).get("summary", "")
    return evaluate_case(req, loaded, verify_threshold)


def main() -> int:
    """Run MVP 4-agent consistency smoke checks."""
    parser = argparse.ArgumentParser(description="4-agent consistency smoke test (MVP)")
    parser.add_argument("--case", action="append", help="Requirement text (repeatable)")
    parser.add_argument("--result-json", default=None, help="Existing workflow result JSON path for offline check")
    parser.add_argument("--verify-threshold", type=float, default=30.0, help="Verify score threshold (0-100)")
    parser.add_argument(
        "--output",
        default=str(_workspace_root() / "data/workspace/test_output/four_agent_consistency_smoke_mvp.json"),
        help="Output JSON report path",
    )
    args = parser.parse_args()

    cases = args.case if args.case else DEFAULT_CASES

    report_items: List[Dict[str, Any]] = []
    if args.result_json:
        report_items.append(run_case_offline(cases[0] if cases else "", args.result_json, args.verify_threshold))
    else:
        for idx, requirement in enumerate(cases, 1):
            print(f"[mvp case {idx}] {requirement}")
            try:
                item = run_case_online(requirement, args.verify_threshold)
            except Exception as exc:
                item = {
                    "requirement": requirement,
                    "error": str(exc),
                    "checks": {
                        "framework_minimal_valid": {"pass": False, "score": 0, "issues": ["workflow execution failed"]},
                        "nlp_json_high_alignment": {"pass": False, "score": 0, "issues": ["workflow execution failed"]},
                        "verify_score_gate": {
                            "pass": False,
                            "score": 0,
                            "threshold": args.verify_threshold,
                            "issues": ["workflow execution failed"],
                        },
                    },
                }
            report_items.append(item)

    overall_pass = all(
        item.get("checks", {}).get("framework_minimal_valid", {}).get("pass")
        and item.get("checks", {}).get("nlp_json_high_alignment", {}).get("pass")
        and item.get("checks", {}).get("verify_score_gate", {}).get("pass")
        for item in report_items
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_pass": overall_pass,
        "mode": "mvp",
        "rules": [
            "framework_minimal_valid",
            "nlp_semantics_json_semantics_high_alignment",
            "verify_score_gate",
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
