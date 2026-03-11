#!/usr/bin/env python3
"""Cloud model pull + multi-agent smoke test.

This script validates:
1) Cloud LLM API connectivity via standard OpenAI-compatible API
2) End-to-end pre-manager workflow (parser -> architect -> ppa)
"""

from __future__ import annotations

import argparse
import sys

try:
    from ._bootstrap import ensure_project_root
except ImportError:
    from _bootstrap import ensure_project_root

ensure_project_root()

from langchain_openai import ChatOpenAI

from app.llm_config import resolve_agent_llm_config
from app.workflow import run_pre_manager_workflow


def cloud_api_smoke(require_cloud: bool = False) -> bool:
    """Validate cloud model connectivity with a minimal call."""
    cfg = resolve_agent_llm_config(
        "pre_agent",
        model_name=None,
        temperature=0.0,
    )

    if not cfg["api_key"]:
        print("⚠️ 未检测到云端API Key，跳过云端连通测试")
        return not require_cloud

    try:
        llm = ChatOpenAI(
            model=cfg["model_name"],
            temperature=0.0,
            max_tokens=16,
            openai_api_key=cfg["api_key"],
            openai_api_base=cfg["api_base"],
        )
        reply = llm.invoke("Reply with exactly: OK")
        content = getattr(reply, "content", "")
        print(f"✅ 云端模型连通成功: model={cfg['model_name']}")
        print(f"   返回: {str(content)[:80]}")
        return True
    except Exception as exc:
        print(f"❌ 云端模型连通失败: {exc}")
        return False


def multi_agent_smoke() -> bool:
    """Run multi-agent pre-manager workflow smoke test."""
    requirement = "设计一个最简单的8位乘法器。"
    try:
        result = run_pre_manager_workflow(requirement, language="zh", source="smoke")
    except Exception as exc:
        print(f"❌ 多Agent工作流执行失败: {exc}")
        return False

    intent = result.get("intent")
    architecture = result.get("architecture")
    ppa = result.get("ppa")

    if not intent or not architecture or not ppa:
        print("❌ 多Agent输出不完整（缺少 intent/architecture/ppa）")
        return False

    print("✅ 多Agent工作流冒烟通过")
    print(f"   intent.summary: {intent.get('summary', '')[:60]}")
    print(f"   top module: {architecture.get('hierarchy', {}).get('top', {}).get('name', 'N/A')}")
    print(f"   feasibility: {ppa.get('feasibility', 'N/A')}")
    return True


def main() -> int:
    """Run cloud connectivity and pre-manager workflow smoke tests."""
    parser = argparse.ArgumentParser(description="Cloud + Multi-Agent smoke test")
    parser.add_argument(
        "--require-cloud",
        action="store_true",
        help="Fail if cloud API is not configured or unavailable",
    )
    args = parser.parse_args()

    print("=" * 68)
    print("AGVS4RTL 云端模型 + 多Agent 冒烟测试")
    print("=" * 68)

    cloud_ok = cloud_api_smoke(require_cloud=args.require_cloud)
    workflow_ok = multi_agent_smoke()

    all_ok = cloud_ok and workflow_ok
    print("\n" + "=" * 68)
    print("结果汇总")
    print("=" * 68)
    print(f"云端模型连通: {'PASS' if cloud_ok else 'FAIL'}")
    print(f"多Agent工作流: {'PASS' if workflow_ok else 'FAIL'}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
