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
    # --- Utility functions ---
    generate_global_task_id,
    build_task_paths,
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
    # --- Utility functions ---
    "generate_global_task_id",
    "build_task_paths",
]
