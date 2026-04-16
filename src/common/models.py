from __future__ import annotations

from enum import Enum
from typing import List, Dict, Optional, Generic, TypeVar, Literal
from datetime import datetime, timezone
import uuid
import re

from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    field_validator,
    model_validator,
)


# ==========================================
# 0. 通用基础配置
# ==========================================

VERILOG_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
EDGE_ENDPOINT_RE = re.compile(r"^(TOP|[A-Za-z_][A-Za-z0-9_$]*)\.[A-Za-z_][A-Za-z0-9_$]*$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_global_task_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short_uuid = uuid.uuid4().hex[:8]
    return f"TASK_{timestamp}_{short_uuid}"


def _validate_identifier(value: str, field_name: str) -> str:
    if not VERILOG_IDENTIFIER_RE.match(value):
        raise ValueError(f"{field_name}='{value}' is not a valid Verilog/SystemVerilog identifier")
    return value

def _validate_non_empty_str(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")
    return value

def _validate_non_empty_str_list(values: List[str], field_name: str) -> List[str]:
    for item in values:
        if not item.strip():
            raise ValueError(f"{field_name} contains empty item")
    return values

def _validate_optional_non_empty_str(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return value
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")
    return value

def _index_ports_by_name(ports: List["PortDef"]) -> Dict[str, "PortDef"]:
    return {p.name: p for p in ports}

def _index_nodes_by_id(nodes: List["RtlNode"]) -> Dict[str, "RtlNode"]:
    return {n.node_id: n for n in nodes}

class StrictBaseModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=False,
    )


# ==========================================
# 1. 强类型枚举库
# ==========================================

class RefactorLevel(str, Enum):
    NONE = "NONE"
    CODE_REWRITE = "CODE_REWRITE"
    ARCH_REFACTOR = "ARCH_REFACTOR"


class IntentCategory(str, Enum):
    GEN_WITH_TEST = "GEN_WITH_TEST"
    GEN_ONLY = "GEN_ONLY"
    MODIFY_EXISTING = "MODIFY_EXISTING"
    FIX_BUG = "FIX_BUG"
    VERIFY_ONLY = "VERIFY_ONLY"


class PortDirection(str, Enum):
    INPUT = "input"
    OUTPUT = "output"
    INOUT = "inout"


class PortType(str, Enum):
    WIRE = "wire"
    REG = "reg"
    LOGIC = "logic"


class ResetType(str, Enum):
    SYNC_HIGH = "sync_high"
    SYNC_LOW = "sync_low"
    ASYNC_HIGH = "async_high"
    ASYNC_LOW = "async_low"


class VerifyVerdict(str, Enum):
    PASS = "PASS"
    FAIL_SEMANTIC = "FAIL_SEMANTIC"
    FAIL_COMPILE = "FAIL_COMPILE"
    FAIL_SIMULATION = "FAIL_SIMULATION"
    TIMEOUT = "TIMEOUT"
    INFRA_ERROR = "INFRA_ERROR"


class NodeType(str, Enum):
    INSTANCE = "instance"
    COMBINATIONAL = "combinational"
    SEQUENTIAL = "sequential"


class ArtifactSourceStage(str, Enum):
    PARSER = "parser"
    ARCHITECT = "architect"
    CODER = "coder"
    VERIFY = "verify"
    WORKFLOW = "workflow"
    USER = "user"


class PathKind(str, Enum):
    ABSOLUTE = "absolute"
    WORKSPACE_RELATIVE = "workspace_relative"


# ==========================================
# 2. 核心基础类
# ==========================================

class BaseSyncMeta(StrictBaseModel):
    task_id: str = Field(default_factory=generate_global_task_id, description="全局唯一流水号")
    iteration: int = Field(default=0, ge=0, description="当前任务的流转轮次")
    refactor_label: RefactorLevel = Field(default=RefactorLevel.NONE, description="重构状态标记")
    intent: IntentCategory = Field(..., description="任务核心意图")
    top_module: str = Field(..., description="目标顶层模块名")
    created_at: datetime = Field(default_factory=_utc_now, description="对象创建 UTC 时间戳")
    source_stage: Optional[ArtifactSourceStage] = Field(default=None, description="产出该对象的来源阶段")

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("task_id cannot be empty")
        return v

    @field_validator("top_module")
    @classmethod
    def validate_top_module(cls, v: str) -> str:
        return _validate_identifier(v, "top_module")


# ==========================================
# 3. 通用子结构
# ==========================================

class PathRef(StrictBaseModel):
    path: str = Field(..., description="路径字符串")
    kind: PathKind = Field(default=PathKind.ABSOLUTE, description="路径类型")
    description: str = Field(default="", description="路径用途说明")

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("path cannot be empty")
        return v


class ParameterDef(StrictBaseModel):
    name: str = Field(..., description="全大写参数名")
    default_value: str = Field(..., description="默认值，支持字符串表达式")
    description: str = Field(default="", description="参数功能说明")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        _validate_identifier(v, "parameter.name")
        if v.upper() != v:
            raise ValueError(f"parameter.name='{v}' should be uppercase by convention")
        return v


class PortDef(StrictBaseModel):
    name: str = Field(..., description="规范的端口名")
    direction: PortDirection
    net_type: PortType = Field(default=PortType.WIRE, description="信号类型")
    width: str = Field(default="1", description="位宽描述")
    clock_domain: Optional[str] = Field(default=None, description="绑定的时钟域；纯组合或异步信号可为空")
    is_clock: bool = Field(default=False, description="是否为时钟端口")
    is_reset: bool = Field(default=False, description="是否为复位端口")
    description: str = Field(default="", description="端口功能说明")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_identifier(v, "port.name")

    @field_validator("clock_domain")
    @classmethod
    def validate_clock_domain(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_identifier(v, "port.clock_domain")

    @field_validator("width")
    @classmethod
    def validate_width(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("port.width cannot be empty")
        return v

    @model_validator(mode="after")
    def validate_port_semantics(self) -> "PortDef":
        if self.is_clock and self.direction != PortDirection.INPUT:
            raise ValueError(f"clock port '{self.name}' must be input")
        if self.is_clock and self.is_reset:
            raise ValueError(f"port '{self.name}' cannot be both clock and reset")
        return self


class ClockResetDef(StrictBaseModel):
    clock_name: str = Field(..., description="时钟端口名")
    reset_name: str = Field(..., description="关联的复位端口名")
    reset_type: ResetType = Field(..., description="复位极性与同步机制")

    @field_validator("clock_name", "reset_name")
    @classmethod
    def validate_names(cls, v: str) -> str:
        return _validate_identifier(v, "clock/reset name")


class ProtocolGroup(StrictBaseModel):
    protocol_type: str = Field(..., description="标准协议名，如 AXI4-Lite")
    role: str = Field(..., description="角色，如 Master/Slave")
    port_mapping: Dict[str, str] = Field(..., description="标准信号到物理端口的映射")
    description: str = Field(default="", description="协议补充说明")

    @field_validator("protocol_type", "role")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("protocol_type/role cannot be empty")
        return v

    @field_validator("port_mapping")
    @classmethod
    def validate_port_mapping(cls, v: Dict[str, str]) -> Dict[str, str]:
        if not v:
            raise ValueError("protocol.port_mapping cannot be empty")
        for logical_name, physical_name in v.items():
            if not logical_name.strip():
                raise ValueError("protocol logical signal name cannot be empty")
            _validate_identifier(physical_name, f"protocol.port_mapping['{logical_name}']")
        return v


class RtlNode(StrictBaseModel):
    node_id: str = Field(..., description="节点唯一标识，如 u_fetch_unit 或 blk_adder")
    node_type: NodeType = Field(default=NodeType.INSTANCE, description="节点类型")
    module_name: Optional[str] = Field(default=None, description="若是子模块例化，对应的模块名")
    description: str = Field(default="", description="节点功能描述与内部逻辑说明")
    is_leaf: bool = Field(default=False, description="是否为不可再分的叶子节点")

    @field_validator("node_id")
    @classmethod
    def validate_node_id(cls, v: str) -> str:
        return _validate_identifier(v, "node.node_id")

    @field_validator("module_name")
    @classmethod
    def validate_module_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_identifier(v, "node.module_name")

    @model_validator(mode="after")
    def validate_node_consistency(self) -> "RtlNode":
        if self.node_type == NodeType.INSTANCE and not self.module_name:
            raise ValueError(f"instance node '{self.node_id}' must provide module_name")
        if self.node_type in {NodeType.COMBINATIONAL, NodeType.SEQUENTIAL}:
            if self.module_name is not None:
                raise ValueError(f"leaf logic node '{self.node_id}' should not provide module_name")
            if not self.is_leaf:
                raise ValueError(f"node '{self.node_id}' with type '{self.node_type}' must be leaf")
        return self


class EndpointRef(StrictBaseModel):
    node_id: str = Field(..., description="节点 ID；顶层统一使用 TOP")
    port_name: str = Field(..., description="端口名")

    @field_validator("node_id")
    @classmethod
    def validate_node_id(cls, v: str) -> str:
        if v == "TOP":
            return v
        return _validate_identifier(v, "endpoint.node_id")

    @field_validator("port_name")
    @classmethod
    def validate_port_name(cls, v: str) -> str:
        return _validate_identifier(v, "endpoint.port_name")


class RtlEdge(StrictBaseModel):
    source: EndpointRef = Field(..., description="驱动端节点及端口")
    target: EndpointRef = Field(..., description="接收端节点及端口")
    signal_name: str = Field(..., description="连线使用的线网名称")
    width: str = Field(default="1", description="连线位宽")
    description: str = Field(default="", description="连线补充说明")

    @field_validator("signal_name")
    @classmethod
    def validate_signal_name(cls, v: str) -> str:
        return _validate_identifier(v, "edge.signal_name")

    @field_validator("width")
    @classmethod
    def validate_width(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("edge.width cannot be empty")
        return v

    @model_validator(mode="after")
    def validate_edge_consistency(self) -> "RtlEdge":
        if self.source == self.target:
            raise ValueError("edge source and target cannot be identical")
        return self

class TaskPaths(StrictBaseModel):
    task_id: str = Field(..., description="任务 ID")
    output_root: str = Field(..., description="输出根目录")
    shared_workspace_root: str = Field(..., description="共享工作区根目录")

    output_task_dir: str = Field(..., description="Output/TASK_ID")
    origin_dir: str = Field(..., description="原始输入目录")
    archive_dir: str = Field(..., description="归档目录")
    result_dir: str = Field(..., description="结果目录")

    shared_task_dir: str = Field(..., description="SharedWorkspace/TASK_ID")
    specs_dir: str = Field(..., description="共享规约目录")
    rtl_dir: str = Field(..., description="共享 RTL 目录")
    sim_dir: str = Field(..., description="共享仿真目录")

    user_task_spec_path: str = Field(..., description="UserTaskSpec.json 路径")

    @field_validator(
        "task_id",
        "output_root",
        "shared_workspace_root",
        "output_task_dir",
        "origin_dir",
        "archive_dir",
        "result_dir",
        "shared_task_dir",
        "specs_dir",
        "rtl_dir",
        "sim_dir",
        "user_task_spec_path",
    )
    @classmethod
    def validate_non_empty(cls, v: str, info) -> str:
        return _validate_non_empty_str(v, f"TaskPaths.{info.field_name}")

def build_task_paths(task_id: str, output_root: str, shared_workspace_root: str) -> TaskPaths:
    output_task_dir = f"{output_root.rstrip('/')}/{task_id}"
    shared_task_dir = f"{shared_workspace_root.rstrip('/')}/{task_id}"

    return TaskPaths(
        task_id=task_id,
        output_root=output_root,
        shared_workspace_root=shared_workspace_root,
        output_task_dir=output_task_dir,
        origin_dir=f"{output_task_dir}/Origin",
        archive_dir=f"{output_task_dir}/Archive",
        result_dir=f"{output_task_dir}/Result",
        shared_task_dir=shared_task_dir,
        specs_dir=f"{shared_task_dir}/specs",
        rtl_dir=f"{shared_task_dir}/rtl",
        sim_dir=f"{shared_task_dir}/sim",
        user_task_spec_path=f"{output_task_dir}/UserTaskSpec.json",
    )

# ==========================================
# 4. UserTaskSpec - Parser 产出
# ==========================================

class UserTaskSpec(BaseSyncMeta):
    prompt_workspace_path: str = Field(..., description="原始需求 TXT 在缓存区的文件路径")
    refined_requirements: List[str] = Field(..., min_length=1, description="Parser 提炼后的核心需求列表")

    workspace_dir: str = Field(..., description="本次任务在 SharedWorkspace 中的专属沙盒目录")
    external_source_path: Optional[str] = Field(default=None, description="外部已有源码路径，仅修改/验证任务需要")
    external_target_path: str = Field(..., description="最终产物搬运目标地址")

    target_protocol: Optional[str] = Field(default=None, description="强制总线协议约束")
    design_rules: List[str] = Field(default_factory=list, description="设计红线约束列表")

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

    @field_validator("external_source_path")
    @classmethod
    def validate_optional_path(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("external_source_path cannot be blank")
        return v

    @field_validator("refined_requirements", "design_rules")
    @classmethod
    def validate_text_list(cls, v: List[str]) -> List[str]:
        for item in v:
            if not item.strip():
                raise ValueError("list item cannot be empty")
        return v

    @field_validator("target_protocol")
    @classmethod
    def validate_target_protocol(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("target_protocol cannot be blank")
        return v


# ==========================================
# 5. SpecReg - 规格注册表
# ==========================================

class SpecReg(BaseSyncMeta):
    module_description: str = Field(..., description="模块功能详述")
    parameters: List[ParameterDef] = Field(default_factory=list, description="参数列表")
    ports: List[PortDef] = Field(..., min_length=1, description="物理端口列表")
    clock_and_reset: List[ClockResetDef] = Field(default_factory=list, description="时钟域与复位定义")
    protocols: List[ProtocolGroup] = Field(default_factory=list, description="成品通信协议编组")
    verification_directives: List[str] = Field(default_factory=list, description="测试指导建议")
    functional_requirements: List[str] = Field(default_factory=list, description="用于验证的关键功能要求")
    corner_cases: List[str] = Field(default_factory=list, description="边界场景提示")
    illegal_conditions: List[str] = Field(default_factory=list, description="非法输入/非法状态约束")
    latency_notes: List[str] = Field(default_factory=list, description="时序/延迟相关约束说明")
    nodes: List[RtlNode] = Field(default_factory=list, description="架构节点列表")
    edges: List[RtlEdge] = Field(default_factory=list, description="架构连线列表")

    @field_validator("module_description")
    @classmethod
    def validate_module_description(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("module_description cannot be empty")
        return v

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

    @model_validator(mode="after")
    def validate_spec_consistency(self) -> "SpecReg":
        port_names = {p.name for p in self.ports}
        node_ids = {n.node_id for n in self.nodes}

        if len(port_names) != len(self.ports):
            raise ValueError("duplicate port names found")

        param_names = [p.name for p in self.parameters]
        if len(set(param_names)) != len(param_names):
            raise ValueError("duplicate parameter names found")

        if len(node_ids) != len(self.nodes):
            raise ValueError("duplicate node_id found")

        # 校验 clock/reset 引用
        for cr in self.clock_and_reset:
            if cr.clock_name not in port_names:
                raise ValueError(f"clock '{cr.clock_name}' not found in ports")
            if cr.reset_name not in port_names:
                raise ValueError(f"reset '{cr.reset_name}' not found in ports")

            port_map = _index_ports_by_name(self.ports)
            node_map = _index_nodes_by_id(self.nodes)

            port_names = set(port_map.keys())
            node_ids = set(node_map.keys())

            clk_port = port_map[cr.clock_name]
            rst_port = port_map[cr.reset_name]

            if clk_port.direction != PortDirection.INPUT:
                raise ValueError(f"clock port '{cr.clock_name}' must be input")
            if rst_port.direction != PortDirection.INPUT:
                raise ValueError(f"reset port '{cr.reset_name}' must be input")

        # 标记型语义检查
        for p in self.ports:
            if p.is_clock and p.name not in {cr.clock_name for cr in self.clock_and_reset}:
                raise ValueError(f"port '{p.name}' is marked as clock but not declared in clock_and_reset")
            if p.is_reset and p.name not in {cr.reset_name for cr in self.clock_and_reset}:
                raise ValueError(f"port '{p.name}' is marked as reset but not declared in clock_and_reset")

        # protocol 引用校验
        for proto in self.protocols:
            for logical_sig, physical_port in proto.port_mapping.items():
                if physical_port not in port_names:
                    raise ValueError(
                        f"protocol '{proto.protocol_type}' mapping '{logical_sig} -> {physical_port}' references unknown port"
                    )

        # edge 引用校验
        for edge in self.edges:
            if edge.source.node_id != "TOP" and edge.source.node_id not in node_ids:
                raise ValueError(f"edge source node '{edge.source.node_id}' not found")
            if edge.target.node_id != "TOP" and edge.target.node_id not in node_ids:
                raise ValueError(f"edge target node '{edge.target.node_id}' not found")

            if edge.source.node_id == "TOP" and edge.source.port_name not in port_names:
                raise ValueError(f"edge source TOP port '{edge.source.port_name}' not found")
            if edge.target.node_id == "TOP" and edge.target.port_name not in port_names:
                raise ValueError(f"edge target TOP port '{edge.target.port_name}' not found")

        return self
    
    def port_map(self) -> Dict[str, PortDef]:
        return {p.name: p for p in self.ports}


    def node_map(self) -> Dict[str, RtlNode]:
        return {n.node_id: n for n in self.nodes}


    def has_clock_reset_definition(self) -> bool:
        return len(self.clock_and_reset) > 0


    def top_input_ports(self) -> List[PortDef]:
        return [p for p in self.ports if p.direction == PortDirection.INPUT]


    def top_output_ports(self) -> List[PortDef]:
        return [p for p in self.ports if p.direction == PortDirection.OUTPUT]

    def is_flat_design(self) -> bool:
        return len(self.nodes) == 0


    def is_hierarchical_design(self) -> bool:
        return len(self.nodes) > 0


    def leaf_nodes(self) -> List[RtlNode]:
        return [n for n in self.nodes if n.is_leaf]


    def instance_nodes(self) -> List[RtlNode]:
        return [n for n in self.nodes if n.node_type == NodeType.INSTANCE]

# ==========================================
# 6. VerifyRpt - 验证报告
# ==========================================

class PortMismatch(StrictBaseModel):
    expected_port: str = Field(..., description="期望端口名")
    actual_port: Optional[str] = Field(default=None, description="实际端口名；缺失时可为空")
    detail: str = Field(default="", description="不匹配详情")

    @field_validator("expected_port")
    @classmethod
    def validate_expected_port(cls, v: str) -> str:
        return _validate_identifier(v, "expected_port")

    @field_validator("actual_port")
    @classmethod
    def validate_actual_port(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_identifier(v, "actual_port")


class CompileError(StrictBaseModel):
    file: Optional[str] = Field(default=None, description="报错文件路径")
    line: Optional[int] = Field(default=None, ge=1, description="报错行号")
    category: Optional[str] = Field(default=None, description="错误类别")
    message: str = Field(..., description="编译错误摘要")

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("compile error message cannot be empty")
        return v


class AssertionFailure(StrictBaseModel):
    name: Optional[str] = Field(default=None, description="断言名")
    time_ns: Optional[float] = Field(default=None, ge=0.0, description="失败时间，单位 ns")
    message: str = Field(..., description="失败信息")

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("assertion failure message cannot be empty")
        return v


class ErrorSnapshot(StrictBaseModel):
    mismatched_ports: List[PortMismatch] = Field(default_factory=list, description="接口不匹配详情")
    compile_errors: List[CompileError] = Field(default_factory=list, description="编译器错误摘要")
    failed_assertions: List[AssertionFailure] = Field(default_factory=list, description="仿真断言失败记录")
    infra_errors: List[str] = Field(default_factory=list, description="基础设施异常摘要")
    suggested_fix: Optional[str] = Field(default=None, description="Verify 节点给出的修复建议")

    @field_validator("infra_errors")
    @classmethod
    def validate_infra_errors(cls, v: List[str]) -> List[str]:
        for item in v:
            if not item.strip():
                raise ValueError("infra_errors item cannot be empty")
        return v

    @field_validator("suggested_fix")
    @classmethod
    def validate_suggested_fix(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("suggested_fix cannot be blank")
        return v


class VerifyRpt(BaseSyncMeta):
    verdict: VerifyVerdict = Field(..., description="验证最终判决")
    error_details: ErrorSnapshot = Field(default_factory=ErrorSnapshot, description="报错快照")
    line_coverage_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0, description="行覆盖率")
    toggle_coverage_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0, description="翻转覆盖率")
    sim_log_path: Optional[str] = Field(default=None, description="仿真日志物理路径")
    wave_file_path: Optional[str] = Field(default=None, description="波形文件物理路径")

    @field_validator("sim_log_path", "wave_file_path")
    @classmethod
    def validate_optional_paths(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("path cannot be blank")
        return v

    @model_validator(mode="after")
    def validate_verdict_consistency(self) -> "VerifyRpt":
        details = self.error_details

        if self.verdict == VerifyVerdict.PASS:
            if details.mismatched_ports or details.compile_errors or details.failed_assertions or details.infra_errors:
                raise ValueError("PASS verdict cannot include error details")

        if self.verdict == VerifyVerdict.FAIL_SEMANTIC and not details.mismatched_ports:
            raise ValueError("FAIL_SEMANTIC requires mismatched_ports")

        if self.verdict == VerifyVerdict.FAIL_COMPILE and not details.compile_errors:
            raise ValueError("FAIL_COMPILE requires compile_errors")

        if self.verdict == VerifyVerdict.FAIL_SIMULATION and not details.failed_assertions:
            raise ValueError("FAIL_SIMULATION requires failed_assertions")

        if self.verdict == VerifyVerdict.INFRA_ERROR and not details.infra_errors:
            raise ValueError("INFRA_ERROR requires infra_errors")

        return self
    
    def is_pass(self) -> bool:
        return self.verdict == VerifyVerdict.PASS


    def is_retryable(self) -> bool:
        return self.verdict in {
            VerifyVerdict.FAIL_SEMANTIC,
            VerifyVerdict.FAIL_COMPILE,
            VerifyVerdict.FAIL_SIMULATION,
            VerifyVerdict.TIMEOUT,
        }


    def is_infra_failure(self) -> bool:
        return self.verdict == VerifyVerdict.INFRA_ERROR


    def requires_arch_refactor(self) -> bool:
        return self.verdict == VerifyVerdict.FAIL_SEMANTIC


    def requires_code_rewrite(self) -> bool:
        return self.verdict in {
            VerifyVerdict.FAIL_COMPILE,
            VerifyVerdict.FAIL_SIMULATION,
            VerifyVerdict.TIMEOUT,
        }
    
    def suggested_refactor_level(self) -> RefactorLevel:
        if self.verdict == VerifyVerdict.FAIL_SEMANTIC:
            return RefactorLevel.ARCH_REFACTOR
        if self.verdict in {
            VerifyVerdict.FAIL_COMPILE,
            VerifyVerdict.FAIL_SIMULATION,
            VerifyVerdict.TIMEOUT,
        }:
            return RefactorLevel.CODE_REWRITE
        return RefactorLevel.NONE


# ==========================================
# 7. FastAPI 标准响应体
# ==========================================

T = TypeVar("T")


class ApiResponse(StrictBaseModel, Generic[T]):
    status: Literal["success", "error"] = Field(..., description="响应状态")
    message: str = Field(..., description="状态描述信息")
    data: Optional[T] = Field(default=None, description="可选的业务载荷数据")

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message cannot be empty")
        return v


# ==========================================
# 8. 三服务工作流载荷模型
# ==========================================

class WorkflowRunRequest(StrictBaseModel):
    intent: Optional[IntentCategory] = Field(default=None, description="工作流意图；为空时由 Parser 路由判定")
    top_module: str = Field(..., description="目标顶层模块名")
    refined_requirements: List[str] = Field(default_factory=list, description="提炼后的需求列表")
    raw_input_text: str = Field(default="", description="原始自然语言输入")
    input_filename: str = Field(default="request.txt", description="原始输入落盘文件名")
    output_root: str = Field(default="/app/Output", description="输出归档根目录，建议绝对路径")
    shared_workspace_root: str = Field(default="/app/shared_workspace", description="共享工作区根目录，建议绝对路径")
    max_iterations: int = Field(default=2, ge=1, le=10, description="最大迭代轮次")

    @field_validator("top_module")
    @classmethod
    def validate_top_module(cls, v: str) -> str:
        return _validate_identifier(v, "top_module")

    @field_validator("refined_requirements")
    @classmethod
    def validate_refined_requirements(cls, v: List[str]) -> List[str]:
        for item in v:
            if not item.strip():
                raise ValueError("refined_requirements item cannot be empty")
        return v

    @field_validator("raw_input_text", "input_filename", "output_root", "shared_workspace_root")
    @classmethod
    def validate_non_empty_text(cls, v: str, info) -> str:
        if info.field_name in {"input_filename", "output_root", "shared_workspace_root"} and not v.strip():
            raise ValueError(f"{info.field_name} cannot be empty")
        return v

    @model_validator(mode="after")
    def validate_input_source(self) -> "WorkflowRunRequest":
        if not self.refined_requirements and not self.raw_input_text.strip():
            raise ValueError("either refined_requirements or raw_input_text must be provided")
        return self


class WorkTaskPayload(StrictBaseModel):
    task_id: str = Field(..., description="工作流任务 ID")
    iteration: int = Field(default=0, ge=0, description="当前迭代轮次")
    intent: IntentCategory = Field(..., description="任务意图")
    top_module: str = Field(..., description="目标顶层模块")
    spec_file_path: str = Field(..., description="UserTaskSpec 文件绝对路径")
    shared_task_dir: str = Field(..., description="共享工作区任务目录绝对路径")

    @field_validator("task_id", "spec_file_path", "shared_task_dir")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field cannot be empty")
        return v

    @field_validator("top_module")
    @classmethod
    def validate_top_module(cls, v: str) -> str:
        return _validate_identifier(v, "top_module")
    
    def is_retry_iteration(self) -> bool:
        return self.iteration > 0


class GenNodeOutput(StrictBaseModel):
    spec_file_path: str = Field(..., description="SpecReg 文件路径")
    rtl_path: str = Field(..., description="Coder 生成的 RTL 文件路径")
    summary: str = Field(..., description="对本次生成动作的简短摘要")

    @field_validator("spec_file_path", "rtl_path", "summary")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field cannot be empty")
        return v


class VerifyTaskPayload(StrictBaseModel):
    task: WorkTaskPayload = Field(..., description="原始任务载荷")
    spec_file_path: str = Field(..., description="用于核对接口和生成 Testbench 的 SpecReg 文件路径")
    rtl_path: str = Field(..., description="待验证的 RTL 文件路径")

    @field_validator("spec_file_path", "rtl_path")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field cannot be empty")
        return v


class VerifyNodeOutput(StrictBaseModel):
    report: VerifyRpt = Field(..., description="细粒度的验证报告与错误快照")
    summary: str = Field(..., description="对本次验证动作的简短摘要")

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("summary cannot be empty")
        return v


class WorkflowTraceStep(StrictBaseModel):
    node: str = Field(..., description="状态机节点名")
    status: Literal["success", "error"] = Field(..., description="节点执行状态")
    detail: str = Field(..., description="节点执行详情")
    created_at: datetime = Field(default_factory=_utc_now, description="记录时间戳")
    iteration: int = Field(default=0, ge=0, description="当前轨迹对应的迭代轮次")

    @field_validator("node", "detail")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field cannot be empty")
        return v


class WorkflowRunResult(StrictBaseModel):
    task_id: str = Field(..., description="任务 ID")
    final_stage: str = Field(..., description="最终节点")
    success: bool = Field(..., description="工作流是否成功")
    trace: List[WorkflowTraceStep] = Field(default_factory=list, description="节点执行轨迹")
    gen_output: Optional[GenNodeOutput] = Field(default=None, description="最终成功的生成载荷")
    verify_output: Optional[VerifyNodeOutput] = Field(default=None, description="最终成功的验证载荷")

    @field_validator("task_id", "final_stage")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field cannot be empty")
        return v