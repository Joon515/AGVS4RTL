#!/usr/bin/env python3
"""Smoke test for multi-model behavior routing.

Target behavior:
1) chat model parses user requirement into structured JSON state
2) reasoning model consumes JSON and outputs architecture JSON
3) coding model consumes JSON and outputs Verilog framework
4) reasoning model verifies consistency across all prior outputs
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.ui.config_store import ConfigStore
from app.workflow import run_full_codegen_workflow


def configure_models_for_smoke() -> None:
    """Temporarily set expected model roles in local config."""
    root = Path("/app")
    store = ConfigStore(root)
    config = store.load_config()
    agents = config.setdefault("agents", {})

    pre = agents.get("pre_agent", {})
    pre["model"] = "deepseek-chat"
    pre["api_base"] = pre.get("api_base") or "https://api.deepseek.com"
    pre.setdefault("temperature", 0.0)
    agents["pre_agent"] = pre

    arch = agents.get("architecture_agent", {})
    arch["model"] = "deepseek-reasoner"
    arch["api_base"] = arch.get("api_base") or pre.get("api_base") or "https://api.deepseek.com"
    arch.setdefault("temperature", 0.1)
    if not arch.get("api_key_enc") and pre.get("api_key_enc"):
        arch["api_key_enc"] = pre["api_key_enc"]
    agents["architecture_agent"] = arch

    gen = agents.get("generate_agent", {})
    gen["model"] = "Qwen/Qwen3-Coder-480B-A35B-Instruct"
    gen["api_base"] = gen.get("api_base") or "https://api.siliconflow.cn/v1"
    gen.setdefault("temperature", 0.1)
    agents["generate_agent"] = gen

    verify = agents.get("verify_agent", {})
    verify["model"] = "deepseek-reasoner"
    verify["api_base"] = verify.get("api_base") or pre.get("api_base") or "https://api.deepseek.com"
    verify.setdefault("temperature", 0.0)
    if not verify.get("api_key_enc") and pre.get("api_key_enc"):
        verify["api_key_enc"] = pre["api_key_enc"]
    agents["verify_agent"] = verify

    config["agents"] = agents
    store.save_config(config)


def main() -> int:
    configure_models_for_smoke()

    requirement = "设计一个AXI-Lite 32位寄存器文件，支持4KB地址空间，工作频率200MHz。"
    result = run_full_codegen_workflow(requirement, language="zh", source="smoke")

    intent = result.get("intent")
    generated = result.get("generated_code", {})
    verification = result.get("verification", {})
    verilog = generated.get("content", "")
    round_outputs = result.get("round_outputs", [])

    print("=" * 68)
    print("Dual Model Codegen Smoke")
    print("=" * 68)
    print("intent_exists=", bool(intent))
    print("generated_exists=", bool(generated))
    print("verification_exists=", bool(verification))
    print("code_model=", generated.get("model"))
    print("verify_model=", verification.get("model"))
    print("verify_status=", verification.get("status"))
    print("verify_score=", verification.get("consistency_score"))
    print("has_module_keyword=", "module" in verilog)
    print("round_count=", len(round_outputs))
    print("preview=", verilog[:160].replace("\n", " "))

    ok = (
        bool(intent)
        and bool(generated)
        and bool(verification)
        and ("module" in verilog)
        and verification.get("status") in {"pass", "warn", "fail"}
    )

    out = {
        "intent": intent,
        "generated_code": generated,
        "verification": verification,
        "round_outputs": round_outputs,
    }
    out_path = Path("/app/data/workspace/test_output/dual_model_codegen_smoke.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved=", out_path)

    history_path = Path("/app/data/workspace/test_output/dual_model_codegen_history.jsonl")
    history_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "dual_model_codegen_smoke",
        "intent_summary": (intent or {}).get("summary", ""),
        "generated_model": generated.get("model"),
        "verify_model": verification.get("model"),
        "verify_status": verification.get("status"),
        "has_module": "module" in verilog,
        "round_outputs": round_outputs,
    }
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(history_entry, ensure_ascii=False) + "\n")
    print("history_saved=", history_path)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
