import httpx
import json
import time
import sys

def main():
    url = "http://localhost:8001/v1/workflow/run"
    
    # 模拟用户通过 Web UI 或 CLI 发送的请求
    payload = {
        "top_module": "seq_done_logic",
        # 故意不在 payload 中显式声明 intent，测试 Parser 的自然语言路由能力
        "raw_input_text": "Please fix the bugs and generate a simple sequential done logic module",
        "refined_requirements": ["reset to 0", "otherwise 1"],
        "max_iterations": 2
    }

    print(f"🚀 [1/3] 发送工作流请求至 Parser 服务: {url}")
    print(f"📦 载荷数据:\n{json.dumps(payload, indent=2, ensure_ascii=False)}")

    start_time = time.time()
    try:
        # 设置较长的超时时间，因为完整的工作流包含多容器调度与大模型调用（预留）
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            
        result = response.json()
        end_time = time.time()
        
        print(f"\n✅ [2/3] 请求完成! 耗时: {end_time - start_time:.2f} 秒")
        
        # =============== 行为校验 ===============
        print("\n🔍 [3/3] 开始校验预期行为...")
        
        assert result["status"] == "success", f"API 调用失败: {result.get('message')}"
        
        data = result.get("data", {})
        trace = data.get("trace", [])
        executed_nodes = [step["node"] for step in trace]
        
        print(f"🛤️  实际执行轨迹: {' -> '.join(executed_nodes)}")
        
        # 核心断言：检查 Parser 冷启动与 Gen 的触发
        assert "parser_initialize" in executed_nodes, "❌ 缺失 parser_initialize 节点 (未创建工作区)"
        assert "gen_stateless" in executed_nodes, "❌ 缺失 gen_stateless 节点 (Gen Agent 未被触发)"
        assert "verify_stateless" in executed_nodes, "❌ 缺失 verify_stateless 节点 (Verify Agent 未被触发)"
        
        # 验证输出产物
        gen_output = data.get("gen_output", {})
        assert gen_output.get("spec_file_path"), "❌ Gen 节点未成功回传 SpecReg 规约文件路径"
        assert gen_output.get("rtl_path"), "❌ Gen 节点未成功回传 RTL 文件路径"
        
        print(f"📄 生成规约落盘于: {gen_output['spec_file_path']}")
        print(f"💻 源码文件落盘于: {gen_output['rtl_path']}")
        print("\n🎉 测试通过！Parser 编排与 Gen Agent 图结构生成的全链路运转正常。")
        
    except httpx.RequestError as e:
        print(f"\n❌ 网络请求异常: {e}")
        print("👉 请确认已经执行了 `docker compose up -d` 并且 Parser 容器正确暴露在了宿主机 8001 端口。")

if __name__ == "__main__":
    main()