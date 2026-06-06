"""
一个不依赖 LLM 的最小 ReAct Loop 示例。

ReAct 的核心循环是：
1. Thought：根据当前状态思考下一步。
2. Action：选择并调用一个工具。
3. Observation：接收工具返回的结果。
4. 重复以上过程，直到选择 finish。

本示例使用固定规则模拟 LLM 的决策过程，方便观察循环本身。
"""

# json 用于把最终状态字典格式化为 JSON 文本。
import json
# sys 用于修改 Python 的模块搜索路径。
import sys
# Path 提供面向对象的跨平台路径操作。
from pathlib import Path
# Any 表示该位置暂时允许任意类型的数据。
from typing import Any


# __file__ 是当前脚本的路径。
# resolve() 得到绝对路径，parents[1] 表示向上两级，得到 day06_react_loop。
DAY_DIR = Path(__file__).resolve().parents[1]
# day06_react_loop 的父目录就是仓库根目录。
ROOT_DIR = DAY_DIR.parent

# 把 day06_react_loop 加入模块搜索路径，使下面可以从 schemas 导入模型。
# append() 会把元素追加到列表末尾；str() 将 Path 转换为普通字符串。
sys.path.append(str(DAY_DIR))

# 导入 ReAct 每一步使用的 Pydantic 数据模型。
# import 放在 sys.path 修改之后，是因为解释器需要先知道去哪里寻找 schemas。
from schemas.react_step_schema import ReactAction, ReactObservation, ReactStep


# Path 对象可以用 / 拼接路径，效果比手写 "\" 或 "/" 更清晰、跨平台。
PROJECT_DIR = ROOT_DIR / "projects" / "agentic_repoops_assistant"
LOG_FILE = DAY_DIR / "logs" / "day06_react_trace.jsonl"


def ensure_demo_project() -> None:
    """确保演示项目和它的 README.md 存在。"""

    # parents=True：缺少的父目录也一并创建。
    # exist_ok=True：目录已存在时不报错。
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)

    # 生成 README.md 的完整路径。
    readme_path = PROJECT_DIR / "README.md"

    # 只有文件不存在时才创建，避免覆盖已有内容。
    if not readme_path.exists():
        # 相邻字符串字面量会由 Python 自动拼接为一个字符串。
        readme_path.write_text(
            "# Agentic RepoOps Assistant\n\n"
            "A repo-oriented engineering agent for issue triage, "
            "file inspection, log diagnosis, and repair planning.\n",
            encoding="utf-8",
        )


def list_project_files(root: str, max_files: int = 50) -> list[str]:
    """
    工具 1：递归列出项目中的文件。

    参数中的 ``max_files: int = 50`` 表示 max_files 是可选参数，
    调用者不传时使用默认值 50。
    """

    # 将字符串路径转换成 Path，便于后续遍历。
    root_path = Path(root)
    # list[str] 表示列表中的每一项都应该是字符串。
    results: list[str] = []

    # rglob("*") 会递归遍历 root_path 下的所有文件和目录。
    for path in root_path.rglob("*"):
        # 如果当前路径不是文件，就跳过本次循环。
        if not path.is_file():
            continue

        # 转换为相对于项目根目录的路径，并统一使用 "/" 分隔。
        rel_path = path.relative_to(root_path).as_posix()

        # 排除 Git 内部文件和 Python 缓存文件。
        if ".git" in rel_path or "__pycache__" in rel_path:
            continue

        # 把符合条件的相对路径加入结果列表。
        results.append(rel_path)

        # 达到数量上限后提前结束循环。
        if len(results) >= max_files:
            break

    # 返回收集到的文件路径。
    return results


def read_text_file(path: str, max_chars: int = 3000) -> str:
    """工具 2：读取文本文件，并限制返回的最大字符数。"""

    # 把传入的字符串转换为 Path。
    file_path = Path(path)

    # 文件不存在时主动抛出异常，让调用者明确知道失败原因。
    if not file_path.exists():
        # f-string 可以把大括号中的变量值嵌入字符串。
        raise FileNotFoundError(f"File not found: {file_path}")

    # errors="ignore" 表示遇到无法解码的字符时忽略它。
    # [:max_chars] 是切片语法，只保留前 max_chars 个字符。
    return file_path.read_text(encoding="utf-8", errors="ignore")[:max_chars]


def search_text(
    root: str,
    query: str,
    max_matches: int = 20,
) -> list[dict[str, Any]]:
    """
    工具 3：在项目的常见文本文件中搜索关键词。

    返回类型 list[dict[str, Any]] 表示：
    外层是列表，每一项是一个键为字符串、值可为任意类型的字典。
    """

    # 搜索的项目根目录。
    root_path = Path(root)
    # 用于保存命中的文件及查询词。
    matches: list[dict[str, Any]] = []

    # 递归遍历目录下的所有路径。
    for path in root_path.rglob("*"):
        # 目录不能读取为文本，因此直接跳过。
        if not path.is_file():
            continue

        # suffix 是文件扩展名；lower() 使扩展名比较不区分大小写。
        if path.suffix.lower() not in [
            ".md",
            ".py",
            ".txt",
            ".json",
            ".yaml",
            ".yml",
        ]:
            continue

        # 读取当前文本文件。
        text = path.read_text(encoding="utf-8", errors="ignore")

        # 两边都调用 lower()，实现简单的不区分大小写搜索。
        if query.lower() in text.lower():
            # append() 把一条结构化搜索结果加入列表。
            matches.append(
                {
                    "file": path.relative_to(root_path).as_posix(),
                    "query": query,
                }
            )

        # 搜索结果达到上限后停止遍历。
        if len(matches) >= max_matches:
            break

    # 返回所有命中结果。
    return matches


def run_tool(action: ReactAction) -> ReactObservation:
    """
    工具路由器：根据 action_name 调用对应的 Python 函数。

    ReactAction 描述“要做什么”，ReactObservation 统一包装执行结果。
    """

    # try/except 用来捕获工具执行中的异常，防止整个 Agent 循环崩溃。
    try:
        # 判断 Agent 选择的是哪个工具。
        if action.action_name == "list_project_files":
            # ** 会把字典拆成关键字参数。
            # 例如 {"root": "...", "max_files": 50}
            # 等价于 list_project_files(root="...", max_files=50)。
            data = list_project_files(**action.action_args)
            return ReactObservation(
                tool_name=action.action_name,
                success=True,
                data=data,
            )

        if action.action_name == "read_text_file":
            data = read_text_file(**action.action_args)
            return ReactObservation(
                tool_name=action.action_name,
                success=True,
                data=data,
            )

        if action.action_name == "search_text":
            data = search_text(**action.action_args)
            return ReactObservation(
                tool_name=action.action_name,
                success=True,
                data=data,
            )

        # finish 是一个终止动作，不需要调用外部工具。
        if action.action_name == "finish":
            return ReactObservation(
                tool_name=action.action_name,
                success=True,
                data="Agent loop finished.",
            )

        # 理论上 Pydantic 会限制 action_name；这里仍保留兜底检查。
        raise ValueError(f"Unknown action: {action.action_name}")

    # Exception 是大多数普通运行时异常的共同父类。
    # as exc 会把捕获到的异常对象保存到变量 exc。
    except Exception as exc:
        # 将异常转换为失败的 Observation，交给 Agent 状态统一处理。
        return ReactObservation(
            tool_name=action.action_name,
            success=False,
            error=str(exc),
        )


def decide_next_action(state: dict[str, Any]) -> tuple[str, ReactAction]:
    """
    最小 Planner：根据已有观察结果决定下一步。

    真实 Agent 通常由 LLM 完成这里的推理。本示例用固定规则模拟，
    返回值 tuple[str, ReactAction] 是“原因文本 + 动作”的二元组。
    """

    # 使用字典下标读取观察历史；键不存在时会抛出 KeyError。
    observations = state["observations"]

    # 空列表在布尔判断中为 False，因此 not observations 表示尚无观察结果。
    if not observations:
        # 用元组一次返回两个值：思考摘要和下一步动作。
        return (
            "当前还没有观察结果，先查看 RepoOps 项目的文件结构。",
            ReactAction(
                action_name="list_project_files",
                action_args={
                    "root": str(PROJECT_DIR),
                    "max_files": 50,
                },
            ),
        )

    # [-1] 表示获取列表中的最后一个元素。
    last_observation = observations[-1]

    # 如果刚刚列出了文件，就根据是否存在 README 决定下一步。
    if last_observation["tool_name"] == "list_project_files":
        # get("data", []) 在 data 不存在时返回空列表，避免 KeyError。
        files = last_observation.get("data", [])

        if "README.md" in files:
            return (
                "已经发现 README.md，下一步读取项目说明。",
                ReactAction(
                    action_name="read_text_file",
                    action_args={
                        "path": str(PROJECT_DIR / "README.md"),
                        "max_chars": 3000,
                    },
                ),
            )

        # 没找到 README 时，改为在项目中搜索 repoops。
        return (
            "没有发现 README.md，搜索 repoops 相关内容。",
            ReactAction(
                action_name="search_text",
                action_args={
                    "root": str(PROJECT_DIR),
                    "query": "repoops",
                    "max_matches": 20,
                },
            ),
        )

    # in 可以判断一个值是否属于列表。
    if last_observation["tool_name"] in ["read_text_file", "search_text"]:
        return (
            "已经获得项目基本信息，可以结束本轮最小 ReAct Loop。",
            ReactAction(
                action_name="finish",
                action_args={},
            ),
        )

    # 任何未覆盖的状态都选择 finish，防止循环失控。
    return (
        "状态已经达到终止条件。",
        ReactAction(
            action_name="finish",
            action_args={},
        ),
    )


def append_log(step: ReactStep) -> None:
    """将一步 ReAct 记录追加到 JSONL 日志文件。"""

    # 确保 logs 目录存在。
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # with 会在代码块结束后自动关闭文件。
    # "a" 是追加模式，不会覆盖之前的日志。
    with LOG_FILE.open("a", encoding="utf-8") as file:
        # model_dump_json() 把 Pydantic 模型序列化为 JSON 字符串。
        # 每条 JSON 独占一行，这种格式称为 JSON Lines（JSONL）。
        file.write(step.model_dump_json() + "\n")


def main() -> None:
    """创建初始状态并运行最多 5 步的 ReAct 循环。"""

    # 在进入循环前准备演示项目。
    ensure_demo_project()

    # state 是 Agent 的共享状态；每一步都读取或更新它。
    state: dict[str, Any] = {
        "run_id": "day06_demo_run",
        "user_goal": (
            "Inspect Agentic RepoOps Assistant project and summarize current status."
        ),
        "belief": {},
        "desire": "Understand current project files and identify next useful action.",
        "intention": None,
        "observations": [],
        "risk_level": "low",
        "need_human_review": False,
        "status": "running",
        "next_action_reason": None,
    }

    # 限制最大步数，防止 Planner 逻辑错误时出现无限循环。
    max_steps = 5

    # range(1, max_steps + 1) 生成 1 到 max_steps，右边界不包含在内。
    for step_id in range(1, max_steps + 1):
        # Python 支持把二元组直接解包到两个变量。
        thought_summary, action = decide_next_action(state)

        # 记录当前意图以及选择这个动作的原因。
        state["intention"] = action.action_name
        state["next_action_reason"] = thought_summary

        # 执行动作，得到统一格式的观察结果。
        observation = run_tool(action)

        # 将 Thought、Action、Observation 和状态变化封装为完整一步。
        step = ReactStep(
            step_id=step_id,
            thought_summary=thought_summary,
            action=action,
            observation=observation,
            state_update={
                "intention": state["intention"],
                "next_action_reason": state["next_action_reason"],
            },
        )

        # model_dump() 把 Pydantic 模型转换为普通 Python 字典。
        state["observations"].append(observation.model_dump())
        # 把本步记录持久化到日志文件。
        append_log(step)

        # f-string 用于把 step_id 等变量嵌入输出文本。
        # 开头的 \n 是换行符，让不同步骤之间更易阅读。
        print(f"\n[STEP {step_id}]")
        print(f"Reason: {thought_summary}")
        print(f"Action: {action.action_name}")
        print(f"Success: {observation.success}")

        # error 为 None 或空字符串时不会进入该分支。
        if observation.error:
            print(f"Error: {observation.error}")

        # Planner 选择 finish 后，更新状态并提前退出 for 循环。
        if action.action_name == "finish":
            state["status"] = "finished"
            break

    # ensure_ascii=False 让中文直接显示，而不是转义为 \uXXXX。
    # indent=2 让 JSON 使用两空格缩进，方便阅读。
    print("\n[FINAL STATE]")
    print(json.dumps(state, indent=2, ensure_ascii=False))


# 只有直接运行本文件时才调用 main()。
# 如果该文件被其他模块 import，下面的代码不会执行。
if __name__ == "__main__":
    main()
