import uuid
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional

from pydantic import BaseModel, Field, ConfigDict

# ============================================================================
# 0. 辅助函数 (Utils)
#   生成全局唯一的任务 ID，格式为: TASK_20240601T123456_1a2b3c4d
# ============================================================================

def generate_global_task_id() -> str:

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"TASK_{timestamp}_{short_uuid}"

# ============================================================================
# 1. 公共元数据底座 (Base Meta Domain)
#    所有跨容器通信的模型都必须继承此处的基类
# ============================================================================

class RefactorLevel(str, Enum):

    NONE = "NONE"                     # 正常迭代，没有发生重构
    CODE_REWRITE = "CODE_REWRITE"     # 局部重写：Verify 跑不通，打回让 Coding 重写代码 (保留原 Spec)
    ARCH_REFACTOR = "ARCH_REFACTOR"   # 架构重构：接口设计有误或死循环，打回让 Architect 重新出规约

class IntentCategory(str, Enum):

    GEN_WITH_TEST = "GEN_WITH_TEST"       # 全新生成 + 测试 (最常见)
    GEN_ONLY = "GEN_ONLY"                 # 仅生成代码 (例如仅出子模块)
    MODIFY_EXISTING = "MODIFY_EXISTING"   # 修改已有代码 + 测试
    FIX_BUG = "FIX_BUG"                   # 基于报错日志修 Bug
    VERIFY_ONLY = "VERIFY_ONLY"           # 仅对已有代码跑回归测试

class BaseSyncMeta(BaseModel):

    model_config = ConfigDict(strict=True)

    task_id: str = Field(default_factory=generate_global_task_id, description="全局唯一流水号")
    iteration: int = Field(default=0, description="当前任务的流转轮次，用于熔断死循环")
    refactor_label: RefactorLevel = Field(default=RefactorLevel.NONE, description="标记当前处于什么级别的重构状态")
    intent: IntentCategory = Field(..., description="任务的核心意图与后续动作变种")
    top_module: str = Field(..., description="目标顶层模块名，用于对齐三个容器的工作焦点")

# ============================================================================
# 2. Parser 领域载荷 (Intent & Routing Domain)
# ============================================================================

class UserTaskSpec(BaseSyncMeta):
    
    # 需求解析
    prompt_workspace_path: str = Field(..., description="原始自然语言 Prompt 在 SharedWorkspace 缓存区的文件路径")
    refined_requirements: List[str] = Field(..., description="Parser 提炼后的核心需求列表")

    # 统一 I/O 管理
    workspace_dir: str = Field(..., description="本次任务在 SharedWorkspace 中的专属沙盒/缓存目录")
    external_source_path: Optional[str] = Field(None, description="系统外部的源码路径 (仅 MODIFY/VERIFY 任务需要)")
    external_target_path: str = Field(..., description="工作流全部 PASS 后，最终产物的目标存储地址")

    # 约束与预设
    target_protocol: Optional[str] = Field(None, description="强制总线协议。如 'AXI4-Lite'")
    design_rules: List[str] = Field(default_factory=list, description="设计红线约束。如 ['no_latch']")

# ============================================================================
# 3. Generator 领域载荷 (Architect & Coding Domain)
# ============================================================================

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

class ParameterDef(BaseModel):

    name: str = Field(..., description="全大写参数名，例如: XLEN")
    default_value: str = Field(..., description="默认值，支持表达式，例如: '32'")
    description: str = Field("", description="参数功能说明")

class PortDef(BaseModel):

    name: str = Field(..., description="严格规范的端口名")
    direction: PortDirection
    net_type: PortType = Field(default=PortType.WIRE, description="信号类型")
    width: str = Field(default="1", description="位宽描述，支持参数化")
    clock_domain: str = Field(..., description="绑定的时钟信号名")

class ClockResetDef(BaseModel):

    clock_name: str = Field(..., description="时钟端口名")
    reset_name: str = Field(..., description="关联的复位端口名")
    reset_type: ResetType = Field(..., description="复位极性与同步机制")

class ProtocolGroup(BaseModel):

    protocol_type: str = Field(..., description="标准协议名，例如: AXI4-Lite")
    role: str = Field(..., description="模块在该协议中的角色，例如: Master")
    port_mapping: Dict[str, str] = Field(..., description="协议标准信号到实际端口的映射")

class SpecReg(BaseSyncMeta):
    
    module_description: str = Field(..., description="具体化的模块功能，用于统一上下文")
    parameters: List[ParameterDef] = Field(default_factory=list, description="参数化设计列表")
    ports: List[PortDef] = Field(..., description="物理端口严格定义")
    clock_and_reset: List[ClockResetDef] = Field(..., description="时钟域与复位树定义")
    protocols: List[ProtocolGroup] = Field(default_factory=list, description="协议编组与端口映射")
    verification_directives: List[str] = Field(default_factory=list, description="测试项目引导与断言预期")

# ============================================================================
# 4. Verify 领域载荷 (Simulation & Validation Domain)
# ============================================================================

class VerifyVerdict(str, Enum):

    PASS = "PASS"                           # 一切完美
    FAIL_SEMANTIC = "FAIL_SEMANTIC"         # 语义空跑失败 (接口/位宽不匹配)
    FAIL_COMPILE = "FAIL_COMPILE"           # 编译失败 (Verilog 语法错误)
    FAIL_SIMULATION = "FAIL_SIMULATION"     # 仿真失败 (逻辑错误或断言触发)

class ErrorSnapshot(BaseModel):

    mismatched_ports: List[str] = Field(default_factory=list, description="语义核查时的接口差异")
    compile_errors: List[str] = Field(default_factory=list, description="编译器 Error 级别行号及原因")
    failed_assertions: List[str] = Field(default_factory=list, description="Cocotb 触发的断言失败记录")
    suggested_fix: Optional[str] = Field(None, description="初步修复建议")

class VerifyRpt(BaseSyncMeta):
    
    verdict: VerifyVerdict = Field(..., description="验证的最终状态")
    error_details: ErrorSnapshot = Field(default_factory=ErrorSnapshot, description="报错快照")
    
    line_coverage_pct: Optional[float] = Field(None, description="行覆盖率百分比")
    toggle_coverage_pct: Optional[float] = Field(None, description="翻转覆盖率百分比")
    
    sim_log_path: Optional[str] = Field(None, description="完整仿真日志路径")
    wave_file_path: Optional[str] = Field(None, description="VCD 波形文件路径")