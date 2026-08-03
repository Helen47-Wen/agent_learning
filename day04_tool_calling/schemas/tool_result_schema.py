from typing import Literal, Any
from pydantic import BaseModel, Field


ToolStatus = Literal["success", "failed", "blocked"]

ErrorType = Literal[
    "none",
    "file_not_found",
    "permission_denied",
    "invalid_path",
    "decode_error",
    "tool_exception",
    "unsafe_operation",
]


class ToolResult(BaseModel):
    tool_name: str = Field(description="工具名称")
    status: ToolStatus = Field(description="工具执行状态")
    message: str = Field(description="面向用户或 Agent 的简要说明")
    data: dict[str, Any] = Field(default_factory=dict, description="工具返回的结构化数据")
    error_type: ErrorType = Field(default="none", description="错误类型")
    elapsed_seconds: float = Field(default=0.0, description="工具执行耗时")