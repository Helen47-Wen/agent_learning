"""
schemas 包的统一出口。

__init__.py 可以先简单理解成：这个文件让 schemas 文件夹变成一个可以被 Python 导入的包，并且决定“从 schemas 这个包里能直接拿到什么东西”。
Python 会先进入 schemas/__init__.py，然后发现里面已经把 IssueTriageDecision 从 issue_triage_schema.py 拿出来放在门口了，于是就能直接导入。

Day03 学习的是 structured output：让模型不要只返回一段自然语言，
而是返回可以被程序验证、解析和继续处理的结构化对象。

这里从具体 schema 文件中导出常用类型，后续代码既可以写：
    from schemas.issue_triage_schema import IssueTriageDecision

也可以写：
    from schemas import IssueTriageDecision
"""

from .issue_triage_schema import (
    IssueTriageDecision,
    IssueType,
    NextAction,
    Priority,
)


__all__ = [
    "IssueTriageDecision",
    "IssueType",
    "NextAction",
    "Priority",
]
