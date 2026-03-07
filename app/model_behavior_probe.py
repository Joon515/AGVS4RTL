#!/usr/bin/env python3
"""Model behavior probe for cloud LLM comparison.

Runs a small suite of prompts against one model and records latency/output stats.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from langchain_openai import ChatOpenAI

from app.llm_config import resolve_agent_llm_config


PROMPTS: List[Dict[str, str]] = [
    {
        "id": "json_parse",
        "prompt": "将这句话转成JSON字段 summary/interfaces: 设计一个最简单的8位乘法器。只输出JSON。",
    },
    {
        "id": "arch_plan",
        "prompt": "给出一个AXI-Lite寄存器文件的3层模块规划（top/mid/leaf），每层不超过3个模块，用中文。",
    },
    {
        "id": "verification",
        "prompt": "给出3条Verilog寄存器文件最关键的自检断言思路，每条一句话。",
    },
]


def run_probe(model_name: str, api_base: str | None, tag: str) -> Dict[str, Any]:
    cfg = resolve_agent_llm_config(
        "pre_agent",
        model_name=model_name,
        temperature=0.0,
        api_base=api_base,
    )

    if not cfg["api_key"]:
        raise RuntimeError("未检测到可用 API Key，请先在配置中设置。")

    llm = ChatOpenAI(
        model=cfg["model_name"],
        temperature=0.0,
        max_tokens=256,
        openai_api_key=cfg["api_key"],
        openai_api_base=cfg["api_base"],
    )

    result_items: List[Dict[str, Any]] = []
    for item in PROMPTS:
        start = time.perf_counter()
        ok = True
        error = None
        content = ""
        try:
            response = llm.invoke(item["prompt"])
            content = str(getattr(response, "content", ""))
        except Exception as exc:
            ok = False
            error = str(exc)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        result_items.append(
            {
                "id": item["id"],
                "ok": ok,
                "latency_ms": latency_ms,
                "output_len": len(content),
                "output_preview": content[:240],
                "error": error,
            }
        )

    now = datetime.now(timezone.utc).isoformat()
    return {
        "tag": tag,
        "timestamp": now,
        "model": cfg["model_name"],
        "api_base": cfg["api_base"],
        "cases": result_items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Model behavior probe")
    parser.add_argument("--model", required=True, help="Model name, e.g. deepseek-chat")
    parser.add_argument("--api-base", default=None, help="OpenAI-compatible base URL")
    parser.add_argument("--tag", default="default", help="Result tag")
    args = parser.parse_args()

    data = run_probe(args.model, args.api_base, args.tag)

    out_dir = Path("/app/data/workspace/test_output")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"model_probe_{args.tag}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"saved={out_path}")
    print(f"model={data['model']}")
    for case in data["cases"]:
        status = "PASS" if case["ok"] else "FAIL"
        print(
            f"{case['id']}: {status}, latency_ms={case['latency_ms']}, output_len={case['output_len']}"
        )
        if case["error"]:
            print(f"  error={case['error']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
