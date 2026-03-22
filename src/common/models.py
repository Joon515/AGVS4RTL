from enum import Enum
from typing import List, Dict, Optional, Any, Generic, TypeVar, Literal
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
import uuid

# ==========================================
# 1. 强类型枚举库 (杜绝大模型幻觉与拼写错误)
# ==========================================

class RefactorLevel(str, Enum):
    NONE = "NONE"                     # 正常迭代
    CODE_REWRITE = "CODE_REWRITE"     # 局部重写代码 (保留原 Spec)
    ARCH_REFACTOR = "ARCH_REFACTOR"   # 架构重构 (推翻重新出规约)

class IntentCategory(str, Enum):
    GEN_WITH_TEST = "GEN_WITH_TEST"       # 全新生成 + 测试
    GEN_ONLY = "GEN_ONLY"                 # 仅生成代码
    MODIFY_EXISTING = "MODIFY_EXISTING"   # 修改已有代码 + 测试
    FIX_BUG = "FIX_BUG"                   # 基于报错日志修 Bug
    VERIFY_ONLY = "VERIFY_ONLY"           # 仅验证

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
    PASS = "PASS"                           # 验证通过
    FAIL_SEMANTIC = "FAIL_SEMANTIC"         # 语义空跑失败 (接口不匹配)
    FAIL_COMPILE = "FAIL_COMPILE"           # 编译失败 (语法错误)
    FAIL_SIMULATION = "FAIL_SIMULATION"     # 仿真失败 (逻辑错误)

# ==========================================
# 2. 辅助函数
# ==========================================

def generate_global_task_id() -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"TASK_{timestamp}_{short_uuid}"

# ==========================================
# 3. 核心基础类 (Message Header)
# ==========================================

class BaseSyncMeta(BaseModel):
    model_config = ConfigDict(strict=True)

    task_id: str = Field(default_factory=generate_global_task_id, description="全局唯一流水号")
    iteration: int = Field(default=0, description="当前任务的流转轮次")
    refactor_label: RefactorLevel = Field(default=RefactorLevel.NONE, description="重构状态标记")
    intent: IntentCategory = Field(..., description="任务核心意图")
    top_module: str = Field(..., description="目标顶层模块名")

# ==========================================
# 4. UserTaskSpec (用户任务规约) - Parser 产出
# ==========================================

class UserTaskSpec(BaseSyncMeta):
    prompt_workspace_path: str = Field(..., description="原始需求 TXT 在缓存区的文件路径")
    refined_requirements: List[str] = Field(..., description="Parser 提炼后的核心需求列表")
    
    workspace_dir: str = Field(..., description="本次任务在 SharedWorkspace 中的专属沙盒目录")
    external_source_path: Optional[str] = Field(None, description="外部已有源码路径 (仅修改/验证任务需要)")
    external_target_path: str = Field(..., description="最终产物搬运目标地址")
    
    target_protocol: Optional[str] = Field(None, description="强制总线协议约束")
    design_rules: List[str] = Field(default_factory=list, description="设计红线约束列表")

# ==========================================
# 5. SpecReg (规格注册表) - Gen (Architect) 产出
# ==========================================

class ParameterDef(BaseModel):
    name: str = Field(..., description="全大写参数名")
    default_value: str = Field(..., description="默认值 (支持字符串表达式)")
    description: str = Field("", description="参数功能说明")

class PortDef(BaseModel):
    name: str = Field(..., description="规范的端口名")
    direction: PortDirection
    net_type: PortType = Field(default=PortType.WIRE, description="信号类型")
    width: str = Field(default="1", description="位宽描述")
    clock_domain: str = Field(..., description="绑定的时钟信号名")

class ClockResetDef(BaseModel):
    clock_name: str = Field(..., description="时钟端口名")
    reset_name: str = Field(..., description="关联的复位端口名")
    reset_type: ResetType = Field(..., description="复位极性与同步机制")

class ProtocolGroup(BaseModel):
    protocol_type: str = Field(..., description="标准协议名 (如 AXI4-Lite)")
    role: str = Field(..., description="角色 (如 Master/Slave)")
    port_mapping: Dict[str, str] = Field(..., description="标准信号到物理端口的映射")

class SpecReg(BaseSyncMeta):
    module_description: str = Field(..., description="模块功能详述")
    parameters: List[ParameterDef] = Field(default_factory=list, description="参数列表")
    ports: List[PortDef] = Field(..., description="物理端口列表")
    clock_and_reset: List[ClockResetDef] = Field(..., description="时钟域与复位定义")
    protocols: List[ProtocolGroup] = Field(default_factory=list, description="成品通信协议编组")
    verification_directives: List[str] = Field(default_factory=list, description="测试指导建议")

# ==========================================
# 6. VerifyRpt (验证报告) - Verify 产出
# ==========================================

class ErrorSnapshot(BaseModel):
    mismatched_ports: List[str] = Field(default_factory=list, description="接口不匹配详情")
    compile_errors: List[str] = Field(default_factory=list, description="编译器错误摘要")
    failed_assertions: List[str] = Field(default_factory=list, description="仿真断言失败记录")
    suggested_fix: Optional[str] = Field(None, description="Verify 节点给出的修复建议")

class VerifyRpt(BaseSyncMeta):
    verdict: VerifyVerdict = Field(..., description="验证最终判决")
    error_details: ErrorSnapshot = Field(default_factory=ErrorSnapshot, description="报错快照")
    
    line_coverage_pct: Optional[float] = Field(None, description="行覆盖率")
    toggle_coverage_pct: Optional[float] = Field(None, description="翻转覆盖率")
    
    sim_log_path: Optional[str] = Field(None, description="仿真日志物理路径")
    wave_file_path: Optional[str] = Field(None, description="波形文件物理路径")

# ==========================================
# 7. FastAPI 标准响应体 (新增)
# ==========================================
T = TypeVar('T')

class ApiResponse(BaseModel, Generic[T]):
    """所有 FastAPI 接口的标准化返回格式"""
    status: str = Field(..., description="'success' 或 'error'")
    message: str = Field(..., description="状态描述信息")
    data: Optional[T] = Field(None, description="可选的业务载荷数据")


# ==========================================
# 8. 三服务工作流载荷模型 (Parser/Gen/Verify)
# ==========================================

class WorkflowRunRequest(BaseModel):
    intent: IntentCategory = Field(default=IntentCategory.GEN_WITH_TEST, description="工作流意图")
    top_module: str = Field(..., description="目标顶层模块名")
    refined_requirements: List[str] = Field(default_factory=list, description="提炼后的需求列表")
    workspace_dir: str = Field(default="/app/shared_workspace", description="共享工作区根目录")


class WorkTaskPayload(BaseModel):
    task_id: str = Field(..., description="工作流任务 ID")
    intent: IntentCategory = Field(..., description="任务意图")
    top_module: str = Field(..., description="目标顶层模块")
    refined_requirements: List[str] = Field(default_factory=list, description="解析后的需求列表")
    workspace_dir: str = Field(..., description="共享工作区根目录")


class GenNodeOutput(BaseModel):
    rtl_path: str = Field(..., description="生成 RTL 目标路径")
    summary: str = Field(..., description="生成摘要")


class VerifyTaskPayload(BaseModel):
    task: WorkTaskPayload = Field(..., description="原始任务载荷")
    rtl_path: str = Field(..., description="待验证 RTL 路径")


class VerifyNodeOutput(BaseModel):
    verdict: VerifyVerdict = Field(..., description="验证判定")
    summary: str = Field(..., description="验证摘要")
    report_path: Optional[str] = Field(None, description="验证报告路径")


class WorkflowTraceStep(BaseModel):
    node: str = Field(..., description="状态机节点名")
    status: Literal["success", "error"] = Field(..., description="节点执行状态")
    detail: str = Field(..., description="节点执行详情")


class WorkflowRunResult(BaseModel):
    task_id: str = Field(..., description="任务 ID")
    final_stage: str = Field(..., description="最终节点")
    success: bool = Field(..., description="工作流是否成功")
    trace: List[WorkflowTraceStep] = Field(default_factory=list, description="节点执行轨迹")
    gen_output: Optional[GenNodeOutput] = Field(None, description="生成节点输出")
    verify_output: Optional[VerifyNodeOutput] = Field(None, description="验证节点输出")