from typing import Literal, Any
from pydantic import BaseModel, Field


ToolName = Literal[
    "list_project_files",
    "read_text_file",
    "search_text",
    "read_recent_log",
    "no_tool",
]


class ToolCallDecision(BaseModel):
    """
    LLM 对下一步工具调用的结构化决策。
    """

    thought: str = Field(description="模型对为什么需要调用该工具的简短说明")

    tool_name: ToolName = Field(description="要调用的工具名称")

    tool_args: dict[str, Any] = Field(
        default_factory=dict,
        description="工具参数"
    )

    risk_level: Literal["low", "medium", "high"] = Field(
        description="本次工具调用风险等级"
    )

    need_human_review: bool = Field(
        description="是否需要人工确认"
    )

    reason: str = Field(
        description="选择该工具的依据"
    )