# LangGraph State Schema（预处理阶段）

本规范定义预处理阶段写入的最小 `state` 结构，用于后续工作流承接。

## 顶层字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| intent | object | 设计意图，见 docs/spec/design-intent.md |
| constraints | object | 结构化约束集合（硬/软） |
| metadata | object | 请求元数据（时间戳、请求ID等） |

## 相关配置规范

- Agent 配置与 API Key 加密存储见: docs/spec/agent-config.md

## constraints 字段

```json
{
  "hard": [
    {"name": "freq", "value": "200MHz", "priority": 0}
  ],
  "soft": [
    {"name": "area", "value": "min", "priority": 1}
  ]
}
```

## metadata 字段

```json
{
  "request_id": "<uuid>",
  "created_at": "2026-02-05T12:00:00+00:00",
  "language": "zh",
  "source": "tui"
}
```
