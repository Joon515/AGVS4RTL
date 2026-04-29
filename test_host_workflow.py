import httpx
import json
import time
import sys


def _post_workflow(url, payload):
    print(f"🚀 发送工作流请求至 Parser 服务: {url}")
    print(f"📦 载荷数据:\n{json.dumps(payload, indent=2, ensure_ascii=False)}")

    start_time = time.time()
    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()

    result = response.json()
    print(f"✅ 请求完成! 耗时: {time.time() - start_time:.2f} 秒")
    assert result["status"] == "success", f"API 调用失败: {result.get('message')}"
    return result


def _executed_nodes(result):
    return [step["node"] for step in result.get("data", {}).get("trace", [])]


def _assert_common_success(result):
    data = result.get("data", {})
    trace = data.get("trace", [])
    executed_nodes = [step["node"] for step in trace]

    print(f"🛤️  实际执行轨迹: {' -> '.join(executed_nodes)}")

    assert data.get("success") is True, f"❌ 工作流未成功: {data}"
    assert data.get("final_stage") == "archive_success", f"❌ 未进入成功归档: {data.get('final_stage')}"
    assert "parser_initialize" in executed_nodes, "❌ 缺失 parser_initialize 节点"
    assert "gen_stateless" in executed_nodes, "❌ 缺失 gen_stateless 节点"
    assert "verify_stateless" in executed_nodes, "❌ 缺失 verify_stateless 节点"

    gen_output = data.get("gen_output", {})
    verify_output = data.get("verify_output", {})
    assert gen_output.get("spec_file_path"), "❌ Gen 节点未成功回传 SpecReg 规约文件路径"
    assert gen_output.get("rtl_path"), "❌ Gen 节点未成功回传 RTL 文件路径"
    assert verify_output.get("report", {}).get("verdict") == "PASS", "❌ 最终 Verify 未 PASS"

    print(f"📄 生成规约落盘于: {gen_output['spec_file_path']}")
    print(f"💻 源码文件落盘于: {gen_output['rtl_path']}")


def run_pass_case(url):
    payload = {
        "top_module": "seq_done_logic",
        "raw_input_text": "Please fix the bugs and generate a simple sequential done logic module",
        "refined_requirements": ["reset to 0", "otherwise 1"],
        "max_iterations": 2,
    }

    print("\n===== PASS 主路径验收 =====")
    result = _post_workflow(url, payload)
    _assert_common_success(result)


def run_retry_semantic_case(url):
    payload = {
        "top_module": "seq_done_retry",
        "raw_input_text": "Generate a simple sequential done logic module and validate retry repair",
        "refined_requirements": [
            "reset to 0",
            "otherwise 1",
            "AGVS4RTL_INJECT_FAIL_SEMANTIC_ONCE",
        ],
        "max_iterations": 2,
    }

    print("\n===== FAIL_SEMANTIC -> retry -> PASS 闭环验收 =====")
    result = _post_workflow(url, payload)
    _assert_common_success(result)

    data = result.get("data", {})
    executed_nodes = _executed_nodes(result)
    assert "prepare_retry" in executed_nodes, "❌ 语义失败场景未进入 prepare_retry"

    retry_steps = [step for step in data.get("trace", []) if step["node"] == "prepare_retry"]
    assert retry_steps and retry_steps[0]["iteration"] == 1, "❌ prepare_retry 未推进到第 1 轮"

    gen_output = data.get("gen_output", {})
    assert "iteration 1" in gen_output.get("summary", ""), "❌ 最终生成结果不是第 1 轮产物"
    assert "FAIL_SEMANTIC" in gen_output.get("summary", ""), "❌ Generator 摘要未体现读取上一轮 VerifyRpt"


def main():
    url = "http://localhost:8001/v1/workflow/run"

    try:
        run_pass_case(url)
        run_retry_semantic_case(url)
        print("\n🎉 测试通过！Parser + Generator + Verify retry 闭环运转正常。")

    except httpx.RequestError as e:
        print(f"\n❌ 网络请求异常: {e}")
        print("👉 请确认已经执行了 `docker compose up -d` 并且 Parser 容器正确暴露在了宿主机 8001 端口。")
        sys.exit(1)

    except AssertionError as e:
        print(f"\n{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()