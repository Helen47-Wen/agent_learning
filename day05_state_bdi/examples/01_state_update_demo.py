"""
演示 RepoOpsState 如何随着 Agent 的执行逐步更新。

本例采用“复制后更新”的方式：函数不直接修改传入的旧状态，而是返回一个
新状态。这样可以保留每一步快照，便于记录日志、调试和恢复任务。
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# ``__file__`` 是当前脚本的路径；resolve() 将它转换为绝对路径。
# parents[0] 是 examples 目录，parents[1] 是 day05_state_bdi 目录。
DAY_DIR = Path(__file__).resolve().parents[1]

# 直接运行 examples 下的脚本时，Python 默认不一定能找到同级的 schemas 包。
# 把 Day 05 根目录加入模块搜索路径后，下面的 import 才能稳定工作。
sys.path.append(str(DAY_DIR))

from schemas.repoops_state import (
    IssueTriageResult,
    RepoOpsState,
    RepoSnapshot,
    ToolObservation,
)


def save_state(state: RepoOpsState, filename: str) -> None:
    """把状态以 JSON 格式保存到 logs 目录。

    ``state: RepoOpsState`` 和 ``filename: str`` 是参数类型标注；
    ``-> None`` 表示函数只执行保存操作，不返回业务结果。
    """

    # pathlib 支持用 / 拼接路径，比手动拼接反斜杠更清晰且可跨平台。
    log_dir = DAY_DIR / "logs"

    # exist_ok=True 表示目录已存在时不报错。
    log_dir.mkdir(exist_ok=True)

    output_path = log_dir / filename

    # model_dump_json() 是 Pydantic 提供的序列化方法。
    # indent=2 让 JSON 带缩进，方便人类阅读。
    output_path.write_text(
        state.model_dump_json(indent=2),
        encoding="utf-8",
    )


def refresh_updated_time(state: RepoOpsState) -> RepoOpsState:
    """复制状态，并把更新时间刷新为当前时间。"""

    # model_copy(update=...) 不会原地修改 state，而会返回更新后的副本。
    return state.model_copy(
        update={
            "updated_at": datetime.now().isoformat(timespec="seconds")
        }
    )


def update_belief_from_files(state: RepoOpsState, files: list[str]) -> RepoOpsState:
    """
    根据工具扫描到的文件列表，更新 Agent 的 Belief。

    ``files: list[str]`` 表示 files 是字符串列表，返回值仍是 RepoOpsState。
    """

    # 列表推导式的结构是：[表达式 for 临时变量 in 可迭代对象]。
    # 先统一路径分隔符和大小写，后续判断就不受 Windows 路径或大小写影响。
    normalized_files = [f.replace("\\", "/").lower() for f in files]

    # any(...) 只要内部有一个条件为 True 就返回 True。
    # 这里传入的是生成器表达式，元素会按需计算，不必先创建完整列表。
    has_readme = any(f in ["readme.md", "readme.txt"] for f in normalized_files)
    has_requirements = any(f == "requirements.txt" for f in normalized_files)
    has_tests = any(f.startswith("tests/") or f.startswith("test_") for f in normalized_files)

    # 先更新嵌套的 Belief，并保留原对象中未写进 update 的其他字段。
    new_belief = state.belief.model_copy(
        update={
            "files": files,
            "has_readme": has_readme,
            "has_requirements": has_requirements,
            "has_tests": has_tests,
        }
    )

    # 工具执行结果也写进状态，后续决策就能知道信息来自哪里。
    new_observation = ToolObservation(
        tool_name="list_project_files",
        status="success",
        message="已根据项目文件列表更新 Belief。",
        data={
            "file_count": len(files),
            "has_readme": has_readme,
            "has_requirements": has_requirements,
            "has_tests": has_tests,
        },
    )

    # ``+ [new_observation]`` 创建新列表，不直接 append 到旧状态的列表中。
    # 这与整个示例“复制后更新”的做法保持一致。
    new_state = state.model_copy(
        update={
            "belief": new_belief,
            "observations": state.observations + [new_observation],
            "status": "running",
        }
    )

    return refresh_updated_time(new_state)


def apply_issue_triage_result(
    state: RepoOpsState,
    triage_result: IssueTriageResult,
) -> RepoOpsState:
    """
    把 Day 03 的 Issue Triage 结构化结果写入 State。
    """

    # triage_result 已经通过 Pydantic 校验，可以安全读取其中的字段。
    new_state = state.model_copy(
        update={
            "issue_triage": triage_result,
            "risk_level": triage_result.risk_level,
            "status": "running",
        }
    )

    return refresh_updated_time(new_state)


def decide_next_intention(state: RepoOpsState) -> RepoOpsState:
    """
    根据当前 Belief 和 Issue 结果，决定下一步 Intention。
    这一步暂时手写规则，后面会改成 LLM + LangGraph 条件路由。
    """

    # 规则有优先级：越需要提前拦截的情况越靠前。
    # 每个分支直接 return，因此命中后不会继续执行下面的规则。
    if state.issue_triage is None:
        return refresh_updated_time(
            state.model_copy(
                update={
                    "intention": "triage_issue",
                    "next_action_reason": "尚未进行 Issue Triage，因此下一步应先分类 Issue。",
                }
            )
        )

    # 信息不足和安全问题都需要人工介入，同时暂停自动执行。
    if state.issue_triage.needs_more_info:
        return refresh_updated_time(
            state.model_copy(
                update={
                    "intention": "ask_human_review",
                    "need_human_review": True,
                    "status": "blocked",
                    "next_action_reason": "Issue 信息不足，需要人工补充信息后再继续。",
                }
            )
        )

    if state.issue_triage.issue_type == "security":
        return refresh_updated_time(
            state.model_copy(
                update={
                    "intention": "ask_human_review",
                    "need_human_review": True,
                    "risk_level": "high",
                    "status": "blocked",
                    "next_action_reason": "安全相关 Issue 必须进入人工复核。",
                }
            )
        )

    if not state.belief.has_readme:
        return refresh_updated_time(
            state.model_copy(
                update={
                    "intention": "final_answer",
                    "next_action_reason": "项目缺少 README，应先建议补充基础说明文档。",
                }
            )
        )

    if state.issue_triage.next_action == "create_fix_plan":
        return refresh_updated_time(
            state.model_copy(
                update={
                    "intention": "create_fix_plan",
                    "next_action_reason": "Issue 信息充分，且下一步建议为创建修复计划。",
                }
            )
        )

    return refresh_updated_time(
        state.model_copy(
            update={
                "intention": "final_answer",
                "next_action_reason": "当前状态没有更具体的工具动作，进入最终答复。",
            }
        )
    )


def build_model_context_from_state(state: RepoOpsState) -> str:
    """
    把完整 State 压缩成适合发给模型的上下文。
    注意：不是把所有日志和历史都塞进去，而是保留关键字段。
    """

    # summary 是普通 Python 字典，只挑选模型完成下一步任务所需的信息。
    # 这种“状态压缩”可以减少无关上下文和 token 消耗。
    summary = {
        "user_goal": state.user_goal,
        "desire": state.desire,
        "belief": {
            "project_root": state.belief.project_root,
            "has_readme": state.belief.has_readme,
            "has_requirements": state.belief.has_requirements,
            "has_tests": state.belief.has_tests,
            "file_count": len(state.belief.files),
        },
        # 这是条件表达式：条件成立取前面的值，否则取 None。
        # model_dump() 会把 Pydantic 模型转换成普通字典。
        "issue_triage": (
            state.issue_triage.model_dump()
            if state.issue_triage
            else None
        ),
        "risk_level": state.risk_level,
        "need_human_review": state.need_human_review,
        "intention": state.intention,
        "next_action_reason": state.next_action_reason,
    }

    # ensure_ascii=False 让中文直接显示，而不是转换成 \uXXXX。
    return json.dumps(summary, ensure_ascii=False, indent=2)


# 只有“直接运行本文件”时，下面的演示代码才会执行。
# 如果其他模块 import 本文件，__name__ 就不是 "__main__"。
if __name__ == "__main__":
    # 1. 初始化 State
    state = RepoOpsState(
        run_id="day05-demo-001",
        user_goal="检查 RepoOps Assistant 项目的当前状态，并判断下一步动作。",
        desire="帮助用户推进 Agentic RepoOps Assistant 项目的工程化实现。",
        belief=RepoSnapshot(
            # 字符串前的 r 表示 raw string（原始字符串），反斜杠不会被当作
            # \n、\t 等转义序列的开头，适合书写 Windows 路径。
            project_root=r"C:\Users\lijic\Desktop\agent_learning\projects\agentic_repoops_assistant"
        ),
    )

    save_state(state, "01_initial_state.json")

    # 2. 模拟 Day 04 文件扫描工具返回
    scanned_files = [
        "README.md",
        "prompts/repoops_system_prompt.md",
        "docs/tool_design.md",
    ]

    state = update_belief_from_files(state, scanned_files)
    save_state(state, "02_after_file_scan.json")

    # 3. 模拟 Day 03 Issue Triage 结果
    triage_result = IssueTriageResult(
        issue_type="bug",
        priority="high",
        needs_more_info=False,
        next_action="create_fix_plan",
        risk_level="low",
        reason="Issue 中包含明确错误：ModuleNotFoundError: No module named 'dotenv'。",
    )

    state = apply_issue_triage_result(state, triage_result)
    save_state(state, "03_after_issue_triage.json")

    # 4. 根据当前 State 决定下一步 Intention
    state = decide_next_intention(state)
    save_state(state, "04_after_intention_decision.json")

    # 5. 构造给模型看的压缩上下文
    model_context = build_model_context_from_state(state)

    print("\n最终 State：")
    print(state.model_dump_json(indent=2))

    print("\n压缩后的模型上下文：")
    print(model_context)
