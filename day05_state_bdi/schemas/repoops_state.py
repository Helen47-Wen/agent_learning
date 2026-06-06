"""
定义 RepoOps Agent 使用的结构化状态。

这里使用 Pydantic 的 ``BaseModel`` 描述数据结构。和普通 Python 类相比，
Pydantic 会在创建对象时检查字段类型，并提供 JSON 序列化、复制等实用方法。
"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ``Literal`` 表示变量只能取列出的字面值。
# 例如 RiskLevel 可以是 "low"，但不能是未声明的 "very_high"。
# 这些名称是“类型别名”，方便多个字段复用同一组约束。
RiskLevel = Literal["low", "medium", "high"]

AgentStatus = Literal[
    "init",
    "running",
    "blocked",
    "failed",
    "completed",
]

Intention = Literal[
    "scan_project",
    "read_readme",
    "triage_issue", # 给 Issue 分类，判断类型、优先级和下一步
    "diagnose_log", #分析日志并诊断问题
    "create_fix_plan",
    "ask_human_review",
    "final_answer",
    "no_action",
]


class RepoSnapshot(BaseModel):
    """
    主要含义：Agent 对当前项目的认知快照，也就是 BDI 中的 Belief。
    主要作用：集中保存项目目录、文件、README、依赖、测试和日志等已知事实，
    为 Agent 后续分析问题和决定下一步动作提供依据。

    ``BaseModel`` 是 Pydantic 的模型基类。继承它后，类中的类型标注
    不只是给编辑器看的，还会参与运行时的数据校验。
    """

    # 没有 default/default_factory 的字段是必填字段。
    project_root: str = Field(description="项目根目录")
    # ``list[str]`` 表示“元素均为字符串的列表”，是 Python 3.9+ 的写法。
    # 可变对象不能直接写成默认值 []，否则可能被多个实例意外共享。
    # ``default_factory=list`` 会在每次创建模型时生成一份新列表。
    files: list[str] = Field(default_factory=list, description="已发现的项目文件")
    has_readme: bool = Field(default=False, description="是否存在 README")
    has_requirements: bool = Field(default=False, description="是否存在 requirements.txt")
    has_tests: bool = Field(default=False, description="是否存在 tests 目录或测试文件")
    recent_logs: list[str] = Field(default_factory=list, description="最近日志摘要")


class IssueTriageResult(BaseModel):
    """
    主要含义：Agent 对一个 Issue 进行分类和初步判断后得到的结构化结果。
    主要作用：保存 Issue 类型、优先级、风险、信息是否充分和建议动作，
    让 Agent 能根据分析结果决定接下来是修复、追问还是请求人工处理。

    这个模型来自 Day 03 的 Issue Triage，并在 Day 05 中成为 State 的一部分。
    """

    # 直接把 Literal 写在字段上，适合只使用一次的取值约束。
    issue_type: Literal[
        "bug",
        "feature",
        "question",
        "documentation",
        "task",
        "security",
        "performance",
        "unknown",
    ]

    priority: Literal["low", "medium", "high", "critical"]
    needs_more_info: bool
    next_action: str
    risk_level: RiskLevel
    reason: str


class ToolObservation(BaseModel):
    """
    主要含义：Agent 调用一次工具后观察到的结果。
    主要作用：记录调用了什么工具、执行是否成功、结果说明以及附加数据，
    避免 Agent 忘记已经做过的操作，并为后续状态更新和决策提供证据。

    这个模型承接 Day 04 的工具执行结果，在这里表示 Agent 获得的新信息。
    """

    tool_name: str
    status: Literal["success", "failed", "blocked"]
    message: str

    # ``dict[str, Any]``：键必须是字符串，值可以是任意类型。
    # Any 适合工具返回结构不固定的场景，但核心字段应尽量使用明确类型。
    data: dict[str, Any] = Field(default_factory=dict)


class RepoOpsState(BaseModel):
    """
    主要含义：Agentic RepoOps Assistant 在某一时刻的完整任务状态。
    主要作用：把用户目标、BDI、Issue 分析、工具观察、风险和运行进度集中起来，
    作为整个 Agent 工作流程中传递、更新、保存和恢复的数据中心。

    BDI 在这里分别对应：
    - Belief：``belief``
    - Desire：``desire``
    - Intention：``intention``

    其他字段用于保存工具观察、风险、运行状态和决策原因。
    """

    run_id: str = Field(description="本次运行 ID")
    user_goal: str = Field(description="用户当前目标")

    belief: RepoSnapshot = Field(description="Agent 当前相信的项目事实")
    desire: str = Field(description="Agent 想要达成的目标")
    intention: Intention = Field(default="scan_project", description="Agent 当前决定执行的下一步动作")

    # Optional[T] 等价于 T | None，表示这个字段可以暂时没有值。
    # 因为 Agent 初始化时还没有执行 Issue 分流，所以默认值设为 None。
    issue_triage: Optional[IssueTriageResult] = Field(
        default=None,
        description="Issue 分流结果",
    )
    observations: list[ToolObservation] = Field(default_factory=list, description="工具观察记录")

    risk_level: RiskLevel = Field(default="low", description="当前整体风险等级")
    need_human_review: bool = Field(default=False, description="是否需要人工确认")
    status: AgentStatus = Field(default="init", description="当前 Agent 运行状态")

    next_action_reason: str = Field(default="", description="为什么选择当前 intention")
    updated_at: str = Field(
        # ``lambda`` 是一个简短的匿名函数。default_factory 会在每次创建状态时
        # 调用它，因此不同状态实例会得到各自的创建时间。
        # isoformat() 生成适合写入 JSON 的 ISO 8601 时间字符串。
        default_factory=lambda: datetime.now().isoformat(timespec="seconds"),
        description="状态更新时间",
    )
