from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ActionName = Literal[
    "list_project_files",
    "read_text_file",
    "search_text",
    "finish",
]


class ReactAction(BaseModel):
    """
    Agent 准备执行的动作。

    注意：
    - action_name 表示要调用哪个工具。
    - action_args 表示调用工具时传入的参数。
    """

    action_name: ActionName
    action_args: dict[str, Any] = Field(default_factory=dict) 
    #action_args 是一个字典。key 是字符串。value 可以是任意类型。
    #如果没有传 action_args，就自动生成一个空字典。


class ReactObservation(BaseModel):
    """
    工具执行后的观察结果。

    Observation 是 ReAct Loop 里的关键概念。
    Agent 不是凭空继续猜，而是根据工具返回的结果继续决策。
    """

    tool_name: str
    success: bool
    data: Any | None = None
    error: str | None = None


class ReactStep(BaseModel):
    """
    ReAct Loop 中的一步完整记录。

    一步通常包括：
    - 决策摘要
    - 动作
    - 工具观察结果
    - 状态更新
    """

    step_id: int
    thought_summary: str
    action: ReactAction
    observation: ReactObservation | None = None
    state_update: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
