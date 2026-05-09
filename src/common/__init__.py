"""
Common models and utilities shared across AGVS4RTL services.

All public symbols from ``src.common.models`` are re-exported here
for convenient single-point imports.
"""

from src.common.models import (
    # --- Base ---
    StrictBaseModel,
    BaseSyncMeta,
    # --- Enums ---
    IntentCategory,
    PortDirection,
    PortType,
    ResetType,
    NodeType,
    RefactorLevel,
    ArtifactSourceStage,
    PathKind,
    VerifyVerdict,
    # --- Sub-structures ---
    PathRef,
    ParameterDef,
    PortDef,
    ClockResetDef,
    ProtocolGroup,
    RtlNode,
    EndpointRef,
    RtlEdge,
    TaskPaths,
    # --- Core models ---
    UserTaskSpec,
    SpecReg,
    PortMismatch,
    CompileError,
    AssertionFailure,
    ErrorSnapshot,
    VerifyRpt,
    ApiResponse,
    HealthStatus,
    LlmRuntimeConfig,
    ParserLlmAnalysis,
    # --- Workflow payloads ---
    WorkflowRunRequest,
    WorkTaskPayload,
    GenNodeOutput,
    VerifyTaskPayload,
    VerifyNodeOutput,
    WorkflowTraceStep,
    WorkflowRunResult,
    # --- Frontend API models ---
    TaskListItem,
    TaskListResponse,
    TaskDetailResponse,
    TaskStatusResponse,
    ServiceHealthItem,
    ServicesHealthResponse,
    # --- Utility functions ---
    generate_global_task_id,
    build_task_paths,
)

from src.common.llm_utils import (
    LLM_HEADER_ENABLED,
    LLM_HEADER_BASE_URL,
    LLM_HEADER_API_KEY,
    LLM_HEADER_MODEL,
    LLM_HEADER_PROFILE,
    _chat_completions_url,
    _extract_json_object,
    _call_openai_compatible_chat,
)

__all__ = [
    # --- Base ---
    "StrictBaseModel",
    "BaseSyncMeta",
    # --- Enums ---
    "IntentCategory",
    "PortDirection",
    "PortType",
    "ResetType",
    "NodeType",
    "RefactorLevel",
    "ArtifactSourceStage",
    "PathKind",
    "VerifyVerdict",
    # --- Sub-structures ---
    "PathRef",
    "ParameterDef",
    "PortDef",
    "ClockResetDef",
    "ProtocolGroup",
    "RtlNode",
    "EndpointRef",
    "RtlEdge",
    "TaskPaths",
    # --- Core models ---
    "UserTaskSpec",
    "SpecReg",
    "PortMismatch",
    "CompileError",
    "AssertionFailure",
    "ErrorSnapshot",
    "VerifyRpt",
    "ApiResponse",
    "HealthStatus",
    "LlmRuntimeConfig",
    "ParserLlmAnalysis",
    # --- Workflow payloads ---
    "WorkflowRunRequest",
    "WorkTaskPayload",
    "GenNodeOutput",
    "VerifyTaskPayload",
    "VerifyNodeOutput",
    "WorkflowTraceStep",
    "WorkflowRunResult",
    # --- Frontend API models ---
    "TaskListItem",
    "TaskListResponse",
    "TaskDetailResponse",
    "TaskStatusResponse",
    "ServiceHealthItem",
    "ServicesHealthResponse",
    # --- Utility functions ---
    "generate_global_task_id",
    "build_task_paths",
    # --- LLM utilities ---
    "LLM_HEADER_ENABLED",
    "LLM_HEADER_BASE_URL",
    "LLM_HEADER_API_KEY",
    "LLM_HEADER_MODEL",
    "LLM_HEADER_PROFILE",
    "_chat_completions_url",
    "_extract_json_object",
    "_call_openai_compatible_chat",
]
