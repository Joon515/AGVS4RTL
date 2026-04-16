已经加了这些辅助函数：

- `_validate_non_empty_str(...)`
- `_validate_optional_non_empty_str(...)`
- `_validate_non_empty_str_list(...)`
- `_validate_identifier(...)`

那下一步最自然的就是把模型里那些重复的 validator 改成统一调用这些函数。

这样有几个好处：

- 错误风格统一
- 后续改规则只改一处
- `model.py` 更短、更清晰
- 降低 copy-paste 失误

---

# 一、统一原则

你现在模型里的重复校验基本分成 4 类：

---

## 1. 非空字符串
原来常见写法：

```python
if not v.strip():
    raise ValueError("xxx cannot be empty")
return v
```

统一成：

```python
return _validate_non_empty_str(v, "xxx")
```

---

## 2. 可选字符串非空
原来常见写法：

```python
if v is None:
    return v
if not v.strip():
    raise ValueError("xxx cannot be blank")
return v
```

统一成：

```python
return _validate_optional_non_empty_str(v, "xxx")
```

---

## 3. 字符串列表项非空
原来常见写法：

```python
for item in v:
    if not item.strip():
        raise ValueError("xxx item cannot be empty")
return v
```

统一成：

```python
return _validate_non_empty_str_list(v, "xxx")
```

---

## 4. 标识符合法性
原来常见写法：

```python
return _validate_identifier(v, "xxx")
```

这一类你已经做得比较统一了，可以继续保持。

---

# 二、你当前代码里最适合统一的地方

我直接按类给你列。

---

## 1. `BaseSyncMeta`

### 现在
```python
@field_validator("task_id")
@classmethod
def validate_task_id(cls, v: str) -> str:
    if not v.strip():
        raise ValueError("task_id cannot be empty")
    return v
```

### 建议改成
```python
@field_validator("task_id")
@classmethod
def validate_task_id(cls, v: str) -> str:
    return _validate_non_empty_str(v, "task_id")
```

---

## 2. `PathRef`

### 现在
```python
@field_validator("path")
@classmethod
def validate_path(cls, v: str) -> str:
    if not v.strip():
        raise ValueError("path cannot be empty")
    return v
```

### 改成
```python
@field_validator("path")
@classmethod
def validate_path(cls, v: str) -> str:
    return _validate_non_empty_str(v, "path")
```

---

## 3. `PortDef`

### `width`
现在：
```python
@field_validator("width")
@classmethod
def validate_width(cls, v: str) -> str:
    if not v.strip():
        raise ValueError("port.width cannot be empty")
    return v
```

改成：
```python
@field_validator("width")
@classmethod
def validate_width(cls, v: str) -> str:
    return _validate_non_empty_str(v, "port.width")
```

### `clock_domain`
现在已经有逻辑分支，这里保留当前形式就行，因为还要做 identifier 校验：

```python
@field_validator("clock_domain")
@classmethod
def validate_clock_domain(cls, v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    return _validate_identifier(v, "port.clock_domain")
```

这个不用强行改成 optional helper，因为它不只是“非空”，还要校验 identifier。

---

## 4. `ProtocolGroup`

### `protocol_type`, `role`
现在：
```python
@field_validator("protocol_type", "role")
@classmethod
def validate_non_empty(cls, v: str) -> str:
    if not v.strip():
        raise ValueError("protocol_type/role cannot be empty")
    return v
```

### 更推荐改成带 `info` 的统一写法
```python
@field_validator("protocol_type", "role")
@classmethod
def validate_non_empty(cls, v: str, info) -> str:
    return _validate_non_empty_str(v, f"protocol.{info.field_name}")
```

这样报错更清楚。

---

## 5. `UserTaskSpec`

### 路径字段
现在：
```python
@field_validator(
    "prompt_workspace_path",
    "workspace_dir",
    "external_target_path",
)
@classmethod
def validate_required_paths(cls, v: str) -> str:
    if not v.strip():
        raise ValueError("required path cannot be empty")
    return v
```

### 改成
```python
@field_validator(
    "prompt_workspace_path",
    "workspace_dir",
    "external_target_path",
)
@classmethod
def validate_required_paths(cls, v: str, info) -> str:
    return _validate_non_empty_str(v, f"UserTaskSpec.{info.field_name}")
```

---

### `external_source_path`
现在：
```python
@field_validator("external_source_path")
@classmethod
def validate_optional_path(cls, v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    if not v.strip():
        raise ValueError("external_source_path cannot be blank")
    return v
```

改成：
```python
@field_validator("external_source_path")
@classmethod
def validate_optional_path(cls, v: Optional[str]) -> Optional[str]:
    return _validate_optional_non_empty_str(v, "UserTaskSpec.external_source_path")
```

---

### `refined_requirements`, `design_rules`
现在：
```python
@field_validator("refined_requirements", "design_rules")
@classmethod
def validate_text_list(cls, v: List[str]) -> List[str]:
    for item in v:
        if not item.strip():
            raise ValueError("list item cannot be empty")
    return v
```

改成：
```python
@field_validator("refined_requirements", "design_rules")
@classmethod
def validate_text_list(cls, v: List[str], info) -> List[str]:
    return _validate_non_empty_str_list(v, f"UserTaskSpec.{info.field_name}")
```

---

### `target_protocol`
现在：
```python
@field_validator("target_protocol")
@classmethod
def validate_target_protocol(cls, v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    if not v.strip():
        raise ValueError("target_protocol cannot be blank")
    return v
```

改成：
```python
@field_validator("target_protocol")
@classmethod
def validate_target_protocol(cls, v: Optional[str]) -> Optional[str]:
    return _validate_optional_non_empty_str(v, "UserTaskSpec.target_protocol")
```

---

## 6. `SpecReg`

### `module_description`
改成：
```python
@field_validator("module_description")
@classmethod
def validate_module_description(cls, v: str) -> str:
    return _validate_non_empty_str(v, "SpecReg.module_description")
```

### 几个文本 list
现在：
```python
@field_validator(
    "verification_directives",
    "functional_requirements",
    "corner_cases",
    "illegal_conditions",
    "latency_notes",
)
@classmethod
def validate_text_list(cls, v: List[str]) -> List[str]:
    for item in v:
        if not item.strip():
            raise ValueError("text list item cannot be empty")
    return v
```

改成：
```python
@field_validator(
    "verification_directives",
    "functional_requirements",
    "corner_cases",
    "illegal_conditions",
    "latency_notes",
)
@classmethod
def validate_text_list(cls, v: List[str], info) -> List[str]:
    return _validate_non_empty_str_list(v, f"SpecReg.{info.field_name}")
```

---

## 7. `CompileError`

### `message`
改成：
```python
@field_validator("message")
@classmethod
def validate_message(cls, v: str) -> str:
    return _validate_non_empty_str(v, "CompileError.message")
```

---

## 8. `AssertionFailure`

### `message`
改成：
```python
@field_validator("message")
@classmethod
def validate_message(cls, v: str) -> str:
    return _validate_non_empty_str(v, "AssertionFailure.message")
```

---

## 9. `ErrorSnapshot`

### `infra_errors`
改成：
```python
@field_validator("infra_errors")
@classmethod
def validate_infra_errors(cls, v: List[str]) -> List[str]:
    return _validate_non_empty_str_list(v, "ErrorSnapshot.infra_errors")
```

### `suggested_fix`
改成：
```python
@field_validator("suggested_fix")
@classmethod
def validate_suggested_fix(cls, v: Optional[str]) -> Optional[str]:
    return _validate_optional_non_empty_str(v, "ErrorSnapshot.suggested_fix")
```

---

## 10. `VerifyRpt`

### `sim_log_path`, `wave_file_path`
改成：
```python
@field_validator("sim_log_path", "wave_file_path")
@classmethod
def validate_optional_paths(cls, v: Optional[str], info) -> Optional[str]:
    return _validate_optional_non_empty_str(v, f"VerifyRpt.{info.field_name}")
```

---

## 11. `ApiResponse`

### `message`
改成：
```python
@field_validator("message")
@classmethod
def validate_message(cls, v: str) -> str:
    return _validate_non_empty_str(v, "ApiResponse.message")
```

---

## 12. `WorkflowRunRequest`

### `refined_requirements`
改成：
```python
@field_validator("refined_requirements")
@classmethod
def validate_refined_requirements(cls, v: List[str]) -> List[str]:
    return _validate_non_empty_str_list(v, "WorkflowRunRequest.refined_requirements")
```

### `input_filename`, `output_root`, `shared_workspace_root`
你现在是混合判断。建议拆清楚一点：

```python
@field_validator("input_filename", "output_root", "shared_workspace_root")
@classmethod
def validate_non_empty_required_text(cls, v: str, info) -> str:
    return _validate_non_empty_str(v, f"WorkflowRunRequest.{info.field_name}")
```

`raw_input_text` 不需要非空校验，因为允许空。

---

## 13. `WorkTaskPayload`

### 这组字段
```python
@field_validator("task_id", "task_spec_path", "shared_task_dir")
@classmethod
def validate_non_empty(cls, v: str) -> str:
    if not v.strip():
        raise ValueError("field cannot be empty")
    return v
```

改成：
```python
@field_validator("task_id", "task_spec_path", "shared_task_dir")
@classmethod
def validate_non_empty(cls, v: str, info) -> str:
    return _validate_non_empty_str(v, f"WorkTaskPayload.{info.field_name}")
```

---

## 14. `GenNodeOutput`

### 现在
```python
@field_validator("spec_reg_path", "rtl_path", "summary")
@classmethod
def validate_non_empty(cls, v: str) -> str:
    if not v.strip():
        raise ValueError("field cannot be empty")
    return v
```

### 改成
```python
@field_validator("spec_reg_path", "rtl_path", "summary")
@classmethod
def validate_non_empty(cls, v: str, info) -> str:
    return _validate_non_empty_str(v, f"GenNodeOutput.{info.field_name}")
```

---

## 15. `VerifyTaskPayload`
如果你已经改名成 `spec_reg_path`，那这里建议：

```python
@field_validator("spec_reg_path", "rtl_path")
@classmethod
def validate_non_empty(cls, v: str, info) -> str:
    return _validate_non_empty_str(v, f"VerifyTaskPayload.{info.field_name}")
```

---

## 16. `VerifyNodeOutput`

```python
@field_validator("summary")
@classmethod
def validate_summary(cls, v: str) -> str:
    return _validate_non_empty_str(v, "VerifyNodeOutput.summary")
```

---

## 17. `WorkflowTraceStep`

```python
@field_validator("node", "detail")
@classmethod
def validate_non_empty(cls, v: str, info) -> str:
    return _validate_non_empty_str(v, f"WorkflowTraceStep.{info.field_name}")
```

---

## 18. `WorkflowRunResult`

```python
@field_validator("task_id", "final_stage")
@classmethod
def validate_non_empty(cls, v: str, info) -> str:
    return _validate_non_empty_str(v, f"WorkflowRunResult.{info.field_name}")
```

---

# 三、推荐一个进一步统一的模式：带 `info` 的 validator

你会发现我上面很多都写成：

```python
def validate_xxx(cls, v: str, info) -> str:
    return _validate_non_empty_str(v, f"ClassName.{info.field_name}")
```

这是我比较推荐的模式，因为它兼顾了：

- 复用辅助函数
- 保留清晰错误信息
- 不用给每个字段手写不同字符串

---

# 四、你可以不统一的地方

有些 validator 不建议硬统一，因为它们除了“非空”之外，还有额外语义。

---

## 不建议强统一 1：`PortDef.clock_domain`
因为它不仅是 optional non-empty，还要是 identifier。

---

## 不建议强统一 2：`ProtocolGroup.port_mapping`
因为这是 dict 的结构校验，不只是字符串非空。

---

## 不建议强统一 3：`RtlNode` / `RtlEdge` / `VerifyRpt` / `SpecReg` 的 `model_validator`
这些是跨字段一致性校验，保留原样最好。

---

# 五、如果你想继续更进一步，可以再补两个 helper

这是可选的。

---

## 1. 标识符 optional 校验函数
如果你后面类似 `clock_domain`、`module_name` 这种 optional identifier 变多，可以加：

```python
def _validate_optional_identifier(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return value
    return _validate_identifier(value, field_name)
```

这样像：

```python
@field_validator("module_name")
@classmethod
def validate_module_name(cls, v: Optional[str]) -> Optional[str]:
    return _validate_optional_identifier(v, "node.module_name")
```

---

## 2. 路径字段统一 helper
如果你们后面想在语义上区分“路径类字段”，可以再加：

```python
def _validate_path_str(value: str, field_name: str) -> str:
    return _validate_non_empty_str(value, field_name)
```

虽然功能一样，但语义更清楚。

---

# 六、最推荐你现在先统一的一批

我建议优先统一这些高频重复点：

1. `BaseSyncMeta.task_id`
2. `UserTaskSpec` 的路径 / list / optional 字段
3. `SpecReg` 的文本字段
4. `WorkTaskPayload`
5. `GenNodeOutput`
6. `VerifyTaskPayload`
7. `WorkflowTraceStep`
8. `WorkflowRunResult`

这一批改完，重复代码会明显少很多。