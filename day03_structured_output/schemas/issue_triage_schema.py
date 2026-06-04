"""
Issue triage 的结构化输出 schema。

这个文件是 Day03 的核心：它用 Pydantic 描述“模型最终应该输出什么结构”。
在 examples/01_issue_triage_parser.py 中，模型先输出 JSON，然后程序用
IssueTriageDecision.model_validate(raw_json) 校验并转换成 Python 对象。

学习重点：
1. Literal 用来限制字段只能取固定枚举值。
2. BaseModel 用来定义结构化结果的字段集合。
3. Field(description=...) 用来说明字段含义，也可以作为写 prompt 时的参考。
4. model_validate(...) 会把模型输出从“不可靠文本”变成“可验证数据”。
"""

from typing import Literal

from pydantic import BaseModel, Field


# IssueType 限制模型只能从这些 Issue 类型中选择一个，避免输出随意的新分类。
IssueType = Literal[
    "bug",
    "feature",
    "question",
    "documentation",
    "task",
    "security",
    "performance",
    "unknown",
]


# Priority 限制优先级取值，方便后续排序、告警或路由到不同处理流程。
Priority = Literal[
    "low",
    "medium",
    "high",
    "critical",
]


# NextAction 表示 triage 之后建议系统或维护者执行的下一步动作。
NextAction = Literal[
    "ask_for_reproduction",
    "request_more_info",
    "assign_to_maintainer",
    "create_fix_plan",
    "add_to_backlog",
    "close_as_duplicate",
    "escalate_security_review",
    "no_action",
]


class IssueTriageDecision(BaseModel):
    """
    RepoOps Assistant 对一个 Issue 的结构化分流判断。

    这个模型相当于“模型输出合同”：只要 LLM 输出的 JSON 能通过它校验，
    后续程序就可以稳定读取 issue_type、priority、next_action 等字段。
    """

    issue_type: IssueType = Field(
        description="Issue 类型，例如 bug、feature、security 或 unknown。"
    )

    priority: Priority = Field(
        description="Issue 优先级，用于判断处理顺序。"
    )

    needs_more_info: bool = Field(
        description="是否需要用户补充更多信息；信息不足时应为 true。"
    )

    suggested_labels: list[str] = Field(
        default_factory=list,
        description="建议添加到 Issue 上的标签列表；没有建议时返回空列表。"
    )

    next_action: NextAction = Field(
        description="建议下一步动作，例如请求更多信息、制定修复计划或进入安全评审。"
    )

    assigned_role: Literal[
        "maintainer",
        "developer",
        "docs_writer",
        "security_reviewer",
        "qa_engineer",
        "none",
    ] = Field(
        description="建议交给哪个角色处理；暂时无需分配时使用 none。"
    )

    risk_level: Literal[
        "low",
        "medium",
        "high",
    ] = Field(
        description="处理该 Issue 的风险等级，用于识别是否需要更谨慎的人工复核。"
    )

    reason: str = Field(
        description="判断依据，说明为什么给出上述分类、优先级和动作。"
    )

    uncertainty: str = Field(
        description="不确定性说明；如果没有明显不确定性，写'无明显不确定性'。"
    )
