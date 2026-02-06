# Agent Config 规范

本规范记录本次对话中新增的配置与界面行为，作为后续开发的统一依据。

## 1. 配置文件位置

- 配置文件: `data/config/agent-config.json`
- 密钥目录: `data/config/keys/`

## 2. 配置结构

```json
{
  "agents": {
    "pre_agent": {
      "model": "gpt-4o-mini",
      "top_k": 40,
      "top_p": 0.9,
      "temperature": 0.7,
      "api_key_enc": {
        "key_id": "<kyber_key_id>",
        "kem_ciphertext": "<base64>",
        "nonce": "<base64>",
        "ciphertext": "<base64>"
      }
    }
  },
  "loop": {
    "global_loop_budget": 3,
    "retry_count_max": 2
  },
  "key_store": {
    "active_key_id": "<kyber_key_id>"
  }
}
```

## 3. TUI 配置入口行为

- 入口: TUI 菜单 `3-参数`
- API Key 必须在 TUI 中输入，不允许从 `.env` 读取
- 支持所有 agent 使用同一 API Key 或分别输入
- 保存时使用 Kyber(PQC) + AES-GCM 加密

## 4. PQC 加密流程

1. 若无 Kyber keypair，生成并写入 `data/config/keys/kyber512_<id>.json`
2. Kyber KEM 生成共享密钥
3. HKDF(SHA-256) 派生 AES-256 Key
4. AES-GCM 加密 API Key
5. 加密结果写入 `agent-config.json`

## 5. TUI 仪表盘数据来源

- 任务列表: `data/workspace/tasks.json`
- 模块架构图: `data/workspace/architecture.txt` 或 `data/workspace/architecture.json`
- 日志入口: `data/log/`
- 预处理输出: `data/workspace/preprocess/<request_id>.json`

## 6. 预处理与输入默认值

- 需求输入: TUI `1-输入` 入口
- 默认字段: `language`, `target_language`, `clock`, `reset`, `interfaces`
- 约束输入: 硬约束/软约束

## 7. 相关实现文件

- TUI: `app/ui/tui.py`
- 配置加密: `app/ui/config_store.py`
- 预处理: `app/pre_agent/stracture_request.py`
- 测试: `app/ui/test_tui.py`, `app/ui/demo_tui.py`
