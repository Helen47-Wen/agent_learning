"""
RepoOps Assistant v0：一个只读的、基于 ReAct 思路运行的仓库分析 Agent。

一、程序作用
1. 接收一个“分析代码仓库”的用户目标。
2. 让大模型（Planner）根据当前状态选择下一步动作。
3. 由 Python 执行受限制的只读工具，而不是让大模型直接操作文件。
4. 把工具结果保存为 Observation，再交给大模型规划下一步。
5. 重复“规划 -> 执行 -> 观察 -> 更新状态”，直到模型选择 finish，
   或达到最大执行步数。
6. 每一步都会追加写入 JSONL 日志，方便排查和复盘 Agent 的决策过程。

二、核心执行链路
main()
  -> run_agent_loop()
     -> build_client()                         创建 OpenAI 客户端
     -> plan_next_action()                     大模型选择一个 ReactAction
        -> build_planner_input()               把当前 State 转成 JSON
        -> Responses API / Chat Completions    获取结构化动作
     -> run_tool()                             Python 执行对应的只读工具
     -> update_state_after_step()              把 Observation 写回 State
     -> append_trace()                         将本步骤追加到 JSONL 日志
     -> 重复以上步骤，直到 finished 或超过 max_steps

三、四个核心数据对象
- ReactAction：大模型决定“下一步做什么”。
- RepoOpsObservation：工具执行后“看到了什么、是否成功”。
- RepoOpsState：一次 Agent 运行期间积累的完整状态。
- RepoOpsStep：Action + Observation + 状态快照组成的一步日志。

四、安全边界
- 仅提供列文件、读文件、搜索文本和结束四种动作。
- resolve_inside_repo() 会阻止读取仓库目录之外的路径。
- 工具执行权始终在 Python 中，大模型只输出结构化决策。

五、本文涉及的 Python 语法速查
- ``name: type``：类型注解，帮助 IDE、Pydantic 和读者理解数据类型。
- ``str | None``：值可以是 str，也可以是 None（Python 3.10+）。
- ``list[str]``：元素类型为 str 的列表（Python 3.9+）。
- ``Literal["a", "b"]``：值只能是列出的字面量之一。
- ``f"{value}"``：f-string，在字符串中插入变量或表达式。
- ``*args`` / ``**kwargs`` 本文件未使用；函数调用主要采用关键字参数，
  例如 ``run_tool(state=state, action=action)``，可读性更好。
- ``try / except``：捕获异常，防止一次工具失败直接中断整个 Agent。
- ``raise ... from ...``：抛出新异常并保留原始异常链。
- ``with``：上下文管理器，文件使用完后会自动关闭。
- 列表推导式 ``[f(x) for x in items]``：简洁地转换或筛选列表。
- ``if __name__ == "__main__"``：仅在直接运行本文件时调用 main()；
  被其他模块 import 时不会自动执行。
"""

# 推迟解析类型注解，减少前向引用问题，也避免部分注解在运行时立即求值。
from __future__ import annotations

# 标准库：JSON 序列化与反序列化。
import json
# 标准库：读取环境变量。
import os
# datetime 类用于生成运行编号和日志时间。
from datetime import datetime
# Path 提供跨平台、面向对象的文件路径操作。
from pathlib import Path
# Any 表示任意类型；Literal 用于限制字符串只能取指定值。
from typing import Any, Literal

# 第三方库：从 .env 文件加载环境变量。
from dotenv import load_dotenv
# OpenAI Python SDK 客户端。
from openai import OpenAI
# Pydantic 用于数据校验、默认值管理和 JSON Schema 生成。
from pydantic import BaseModel, Field, ValidationError, field_validator


# ============================================================
# 1. 基础配置
# ============================================================

# __file__ 是当前源码文件路径；resolve() 转成绝对路径；parent 取父目录。
PROJECT_DIR = Path(__file__).resolve().parent
# v0 默认只分析当前项目目录。
REPO_ROOT = PROJECT_DIR
# Path 对象可用 / 拼接子路径，比手动拼接字符串更安全、清晰。
LOG_DIR = PROJECT_DIR / "logs"
# JSONL 是“一行一个 JSON 对象”的日志格式，适合逐步追加记录。
LOG_FILE = LOG_DIR / "repoops_v0_trace.jsonl"


def now_iso() -> str:
    """
    返回当前时间字符串，用于日志和状态更新时间。
    """
    # -> str 是返回值类型注解；timespec="seconds" 表示精确到秒。
    return datetime.now().isoformat(timespec="seconds")


# ============================================================
# 2. Schema：Action / Observation / State / Step
# ============================================================

# 类型别名：ActionName 的值只能是下面四个字符串之一。
ActionName = Literal[
    "list_project_files",
    "read_text_file",
    "search_text",
    "finish",
]


# 继承 BaseModel 后，Pydantic 会自动完成构造、类型校验和序列化。
class ActionArgs(BaseModel):
    """
    工具参数。

    不同工具会使用不同字段：
    - list_project_files 使用 root / max_files
    - read_text_file 使用 path / max_chars
    - search_text 使用 root / query / max_matches
    """

    # 可选字段以 None 为默认值；具体动作只使用自己需要的字段。
    root: str | None = None
    path: str | None = None
    query: str | None = None
    # 以下字段提供限制值，避免一次返回过多内容。
    max_files: int = 50
    max_chars: int = 3000
    max_matches: int = 20

    @field_validator("max_files", "max_chars", "max_matches", mode="before")
    @classmethod
    def restore_default_limits(cls, value: Any, info: Any) -> int:
        """
        部分兼容模型会把未使用的数字参数返回为 null。

        Pydantic 只有在字段缺失时才使用默认值；显式 null 会被当成 None，
        因而无法通过 int 校验。这里在正式校验前把 null 恢复为字段默认值。
        """
        if value is not None:
            return value

        defaults = {
            "max_files": 50,
            "max_chars": 3000,
            "max_matches": 20,
        }
        return defaults[info.field_name]


class ReactAction(BaseModel):
    """
    大模型 Planner 输出的结构化动作。

    注意：
    模型只负责“决定要做什么”；
    Python 才负责真正执行。
    """

    # Field(description=...) 会把说明写入 JSON Schema，帮助大模型正确填值。
    action_name: ActionName = Field(description="The next tool/action to execute.")
    # default_factory 每次创建模型时生成新的 ActionArgs，避免共享可变默认对象。
    action_args: ActionArgs = Field(default_factory=ActionArgs)
    # 保存 Planner 选择该动作的简短理由。
    reason: str = Field(description="A short reason for choosing this action.")


class RepoOpsObservation(BaseModel):
    """
    工具执行后的观察结果。
    """

    tool_name: str
    success: bool
    # data 的结构因工具而异，所以使用 Any；失败时通常保持为 None。
    data: Any | None = None
    error: str | None = None
    # 传入函数本身而不是 now_iso() 的结果，从而在实例创建时再取时间。
    created_at: str = Field(default_factory=now_iso)


class RepoOpsState(BaseModel):
    """
    RepoOps Assistant v0 的内部状态。
    """

    run_id: str
    user_goal: str
    repo_path: str
    # list[RepoOpsObservation] 表示列表中的每个元素都应是 Observation。
    observations: list[RepoOpsObservation] = Field(default_factory=list)
    # Literal 构成一个简单、受校验的状态机。
    status: Literal["running", "finished", "failed"] = "running"
    risk_level: Literal["low", "medium", "high"] = "low"
    need_human_review: bool = False
    next_action_reason: str | None = None
    final_answer: str | None = None
    updated_at: str = Field(default_factory=now_iso)


class RepoOpsStep(BaseModel):
    """
    一次完整 Agent step 的记录。
    """

    step_id: int
    action: ReactAction
    observation: RepoOpsObservation
    state_status: str
    created_at: str = Field(default_factory=now_iso)


# ============================================================
# 3. 安全路径处理
# ============================================================

def resolve_inside_repo(repo_path: str, user_path: str) -> Path:
    """
    把模型给出的路径解析成真实路径，并确保它在 repo_path 内部。

    这是一个安全边界：
    即使模型给出 C:\\Windows\\xxx 之类路径，也不能读取项目外文件。
    """
    # 将仓库根目录规范化为绝对路径。
    base = Path(repo_path).resolve()
    # 用户或大模型给出的路径可能是相对路径，也可能是绝对路径。
    target = Path(user_path)

    # 相对路径必须以仓库根目录为基准进行拼接。
    if not target.is_absolute():
        target = base / target

    # 解析 .、.. 和符号链接，得到最终真实路径。
    target = target.resolve()

    # 合法情况只有两种：目标就是仓库根目录，或仓库根目录是目标的父目录。
    if target != base and base not in target.parents:
        # 主动拒绝目录穿越，例如 ../../Windows 或仓库外的绝对路径。
        raise ValueError(f"Path is outside repo: {target}")

    # 校验通过后才把路径交给后续文件工具。
    return target


# ============================================================
# 4. 工具函数：只读文件工具
# ============================================================

def list_project_files(repo_path: str, root: str | None = None, max_files: int = 50) -> list[str]:
    """
    列出项目文件。
    """
    # base 始终代表仓库根目录，后续返回路径都相对于它。
    base = Path(repo_path).resolve()

    # root 有值时只遍历指定子目录，否则遍历整个仓库。
    if root:
        root_path = resolve_inside_repo(repo_path, root)
    else:
        root_path = base

    # 显式标注列表元素类型，便于静态检查和阅读。
    results: list[str] = []

    # rglob("*") 会递归遍历 root_path 下的所有目录项。
    for path in root_path.rglob("*"):
        # 目录不是目标，直接进入下一轮循环。
        if not path.is_file():
            continue

        # 转成相对仓库的 POSIX 路径，使输出统一使用 /。
        rel_path = path.relative_to(base).as_posix()

        # 忽略 Git 内部数据和 Python 字节码缓存。
        if ".git" in rel_path or "__pycache__" in rel_path:
            continue

        # 保存符合条件的文件路径。
        results.append(rel_path)

        # 达到上限后立即停止，避免大型仓库产生过多上下文。
        if len(results) >= max_files:
            break

    # 把文件路径列表作为工具结果返回。
    return results


def read_text_file(repo_path: str, path: str, max_chars: int = 3000) -> str:
    """
    读取文本文件。
    """
    # 先做路径安全校验，再访问文件系统。
    file_path = resolve_inside_repo(repo_path, path)

    # exists() 同时适用于文件和目录，因此还需要下面的 is_file()。
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    # errors="ignore" 会跳过无法按 UTF-8 解码的字节；切片限制返回字符数。
    return file_path.read_text(encoding="utf-8", errors="ignore")[:max_chars]


def search_text(
    repo_path: str,
    root: str | None,
    query: str,
    max_matches: int = 20,
) -> list[dict[str, str]]:
    """
    在项目文本文件中搜索关键词。
    """
    # 与列文件工具相同，先确定仓库根目录和搜索起点。
    base = Path(repo_path).resolve()

    if root:
        root_path = resolve_inside_repo(repo_path, root)
    else:
        root_path = base

    # 每条匹配记录都是键和值均为字符串的字典。
    matches: list[dict[str, str]] = []

    # 使用集合保存后缀，成员判断通常比列表更直接、高效。
    allowed_suffixes = {
        ".md",
        ".py",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".env.example",
    }

    # 递归扫描搜索目录。
    for path in root_path.rglob("*"):
        if not path.is_file():
            continue

        # 仅搜索常见文本文件，避免误读图片、压缩包等二进制文件。
        if path.suffix.lower() not in allowed_suffixes:
            continue

        # relative_to() 用于输出相对路径；read_text() 读取完整文本。
        rel_path = path.relative_to(base).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")

        # 两边都转为小写，实现简单的大小写不敏感包含搜索。
        if query.lower() in text.lower():
            matches.append(
                {
                    "file": rel_path,
                    "query": query,
                }
            )

        # 达到匹配数量上限后停止扫描。
        if len(matches) >= max_matches:
            break

    return matches


# ============================================================
# 5. 工具路由器
# ============================================================

def run_tool(state: RepoOpsState, action: ReactAction) -> RepoOpsObservation:
    """
    根据 action_name 执行对应工具。
    """
    # 将所有工具异常统一转换成失败的 Observation，保持循环可继续运行。
    try:
        # 使用局部变量缩短后续字段访问。
        args = action.action_args

        # action_name 相当于路由键，决定调用哪个 Python 函数。
        if action.action_name == "list_project_files":
            data = list_project_files(
                repo_path=state.repo_path,
                root=args.root,
                max_files=args.max_files,
            )
            # 工具成功时立即返回标准化观察结果。
            return RepoOpsObservation(
                tool_name=action.action_name,
                success=True,
                data=data,
            )

        if action.action_name == "read_text_file":
            # read_text_file 的 path 是必填业务参数，需额外校验。
            if not args.path:
                raise ValueError("read_text_file requires action_args.path")

            data = read_text_file(
                repo_path=state.repo_path,
                path=args.path,
                max_chars=args.max_chars,
            )
            return RepoOpsObservation(
                tool_name=action.action_name,
                success=True,
                data=data,
            )

        if action.action_name == "search_text":
            # 空字符串也会被 not 判定为 True，因此不能作为有效查询词。
            if not args.query:
                raise ValueError("search_text requires action_args.query")

            data = search_text(
                repo_path=state.repo_path,
                root=args.root,
                query=args.query,
                max_matches=args.max_matches,
            )
            return RepoOpsObservation(
                tool_name=action.action_name,
                success=True,
                data=data,
            )

        if action.action_name == "finish":
            # finish 不访问文件，只产生一个成功的结束观察结果。
            return RepoOpsObservation(
                tool_name=action.action_name,
                success=True,
                data={
                    "message": "RepoOps Assistant v0 finished.",
                    "reason": action.reason,
                },
            )

        # 理论上 Pydantic 的 Literal 已阻止未知动作，这里再做运行时兜底。
        raise ValueError(f"Unknown action: {action.action_name}")

    # Exception 是大多数常规异常的基类；as exc 将异常对象绑定到变量。
    except Exception as exc:
        return RepoOpsObservation(
            tool_name=action.action_name,
            success=False,
            error=str(exc),
        )


# ============================================================
# 6. LLM Planner
# ============================================================

# 三引号字符串可以自然书写多行文本，这里作为 Planner 的系统提示词。
PLANNER_SYSTEM_PROMPT = """
You are RepoOps Assistant v0.

Your job is to inspect a code/project repository using safe read-only tools.

You must choose exactly one next action from:

1. list_project_files
2. read_text_file
3. search_text
4. finish

Rules:
- Use list_project_files first if you have no observations.
- Prefer reading README.md or docs when available.
- Use search_text when you need to find a keyword.
- Use finish when you have enough information to summarize the project status.
- Do not request destructive actions.
- Do not invent file contents.
- Keep your reason short and practical.

Return a structured ReactAction.

For action_args:
- Omit unused fields when possible.
- Never return null for max_files, max_chars, or max_matches.
"""


def build_client() -> OpenAI:
    """
    初始化 OpenAI SDK 客户端。

    支持：
    - 官方 OpenAI API
    - 部分 OpenAI-compatible API
    """
    # 默认从当前目录或父目录中的 .env 文件加载配置。
    load_dotenv()

    # os.getenv() 在变量不存在时返回 None。
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")

    # API Key 是必需配置，缺失时尽早给出清晰错误。
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in .env")

    # base_url 可选，可用于连接兼容 OpenAI 协议的服务。
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)

    # 未配置 base_url 时使用 SDK 的默认官方地址。
    return OpenAI(api_key=api_key)


def should_use_responses_api() -> bool:
    """
    判断当前服务是否应优先使用 OpenAI Responses API。

    OPENAI_USE_RESPONSES 可显式覆盖自动判断；未配置时，只有官方 OpenAI
    地址默认启用。DeepSeek 等兼容服务通常只实现 Chat Completions。
    """
    configured = os.getenv("OPENAI_USE_RESPONSES")

    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}

    base_url = os.getenv("OPENAI_BASE_URL", "").strip().lower()
    return not base_url or "api.openai.com" in base_url


def compact_observation(obs: RepoOpsObservation, max_chars: int = 1200) -> dict[str, Any]:
    """
    压缩 Observation，避免把太长的文件内容全部塞回模型上下文。
    """
    # 先序列化为字符串，便于统一计算长度；ensure_ascii=False 保留中文。
    data_text = json.dumps(obs.data, ensure_ascii=False)

    # 只截断发给模型的副本，不会修改原始 Observation。
    if len(data_text) > max_chars:
        data_text = data_text[:max_chars] + "...[truncated]"

    # 返回普通字典，稍后会被整体序列化为 Planner 输入。
    return {
        "tool_name": obs.tool_name,
        "success": obs.success,
        "data": data_text,
        "error": obs.error,
        "created_at": obs.created_at,
    }


def build_planner_input(state: RepoOpsState) -> str:
    """
    构造发给模型的当前状态摘要。
    """
    # payload 是发给 Planner 的状态快照，不包含可执行函数本身。
    payload = {
        "user_goal": state.user_goal,
        "repo_path": state.repo_path,
        "status": state.status,
        "risk_level": state.risk_level,
        "need_human_review": state.need_human_review,
        # 只保留最近 5 条观察，避免上下文随循环无限增长。
        "observations": [
            # 列表推导式：对切片得到的每条观察调用压缩函数。
            compact_observation(obs)
            for obs in state.observations[-5:]
        ],
        # 明确告诉模型可用动作及参数，降低它编造工具的概率。
        "available_actions": {
            "list_project_files": {
                "description": "List files under the repo.",
                "args": ["root", "max_files"],
            },
            "read_text_file": {
                "description": "Read a text file inside the repo.",
                "args": ["path", "max_chars"],
            },
            "search_text": {
                "description": "Search text in repo files.",
                "args": ["root", "query", "max_matches"],
            },
            "finish": {
                "description": "Finish the loop when enough information is collected.",
                "args": [],
            },
        },
    }

    # indent=2 让 JSON 更易读；返回值将作为 user 消息发送给模型。
    return json.dumps(payload, ensure_ascii=False, indent=2)


def plan_next_action(client: OpenAI, model: str, state: RepoOpsState) -> ReactAction:
    """
    让大模型基于当前 State 选择下一步动作。

    优先使用 Responses API + Pydantic structured output。
    如果当前模型或兼容 API 不支持，则回退到 Chat Completions JSON 模式。
    """
    # 将当前状态转换为模型可读的 JSON 文本。
    planner_input = build_planner_input(state)

    # 官方 OpenAI 服务优先尝试 Responses API；兼容服务直接走 Chat Completions。
    if should_use_responses_api():
        try:
            response = client.responses.parse(
                model=model,
                # input 是消息列表，每条消息都包含角色和文本内容。
                input=[
                    {
                        "role": "system",
                        "content": PLANNER_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": planner_input,
                    },
                ],
                # SDK 根据 Pydantic 模型生成 Schema，并校验模型返回值。
                text_format=ReactAction,
            )

            # output_parsed 已经是 ReactAction 实例，不再需要手动解析 JSON。
            return response.output_parsed

        # 官方服务或代理若临时不支持 Responses API，则降级一次。
        except Exception as responses_error:
            print("[WARN] Responses structured output failed, fallback to chat JSON mode.")
            print(f"[WARN] {responses_error}")

    # 从 Pydantic 模型生成 JSON Schema，作为 JSON 模式的格式提示。
    schema_hint = ReactAction.model_json_schema()

    # 使用兼容范围更广的 Chat Completions API。
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                # 圆括号允许把多段字符串表达式跨行拼接。
                "content": (
                    PLANNER_SYSTEM_PROMPT
                    + "\nYou must return JSON only. "
                    + "The JSON must match this schema:\n"
                    + json.dumps(schema_hint, ensure_ascii=False)
                ),
            },
            {
                "role": "user",
                "content": planner_input,
            },
        ],
        # JSON mode 只保证输出是 JSON，具体字段仍需 Pydantic 校验。
        response_format={"type": "json_object"},
    )

    # choices[0] 是第一个候选答案；or "{}" 处理 content 为 None 的情况。
    content = completion.choices[0].message.content or "{}"

    try:
        # 从 JSON 字符串创建并校验 ReactAction。
        return ReactAction.model_validate_json(content)
    except ValidationError as validation_error:
        # 报错时附带模型原文，便于定位兼容模型的结构化输出问题。
        raise RuntimeError(
            f"Model returned invalid ReactAction JSON: {content}"
        ) from validation_error


# ============================================================
# 7. 日志与主循环
# ============================================================

def append_trace(step: RepoOpsStep) -> None:
    """
    追加一行 jsonl trace。
    """
    # parents=True 会创建缺失的父目录；exist_ok=True 表示目录已存在也不报错。
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # with 会在代码块结束后自动关闭文件；"a" 表示追加而非覆盖。
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(
                # model_dump() 把 Pydantic 对象递归转换为普通 Python 数据。
                step.model_dump(),
                ensure_ascii=False,
            )
            # 每条记录末尾加换行，从而形成 JSONL 格式。
            + "\n"
        )


def update_state_after_step(
    state: RepoOpsState,
    action: ReactAction,
    observation: RepoOpsObservation,
) -> RepoOpsState:
    """
    根据工具结果更新 Agent State。
    """
    # append() 原地修改列表，把最新观察加入历史记录。
    state.observations.append(observation)
    # 保存本次动作理由，便于展示或调试。
    state.next_action_reason = action.reason
    # 每执行一步都刷新更新时间。
    state.updated_at = now_iso()

    # 工具失败不立即终止循环，但将风险等级提高为 medium。
    if not observation.success:
        state.risk_level = "medium"

    # 只有成功执行 finish 动作，状态机才进入 finished。
    if action.action_name == "finish" and observation.success:
        state.status = "finished"
        state.final_answer = action.reason

    # state 是可变对象；这里返回它是为了让调用链表达得更明确。
    return state


def run_agent_loop(user_goal: str, repo_path: Path, max_steps: int = 6) -> RepoOpsState:
    """
    运行 RepoOps Assistant v0。
    """
    # 创建 API 客户端；配置错误会在进入主循环前暴露。
    client = build_client()
    # 第二个参数是环境变量缺失时使用的默认模型名。
    model = os.getenv("OPENAI_MODEL", "gpt-5.5")

    # 初始化本次运行唯一的状态对象。
    state = RepoOpsState(
        # strftime() 按指定格式生成时间文本，用作可读的运行编号。
        run_id=f"repoops_v0_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        user_goal=user_goal,
        repo_path=str(repo_path.resolve()),
    )

    print("[INFO] RepoOps Assistant v0 started.")
    print(f"[INFO] Model: {model}")
    print(f"[INFO] Repo path: {state.repo_path}")

    # range() 左闭右开，因此 max_steps + 1 才能包含 max_steps。
    for step_id in range(1, max_steps + 1):
        print(f"\n[STEP {step_id}] Planning next action...")

        # 阶段 1：Planner 根据当前状态选择下一动作。
        action = plan_next_action(
            client=client,
            model=model,
            state=state,
        )

        print(f"[ACTION] {action.action_name}")
        print(f"[REASON] {action.reason}")

        # 阶段 2：工具路由器真正执行动作并返回观察结果。
        observation = run_tool(
            state=state,
            action=action,
        )

        print(f"[OBSERVATION] success={observation.success}")

        if observation.error:
            print(f"[ERROR] {observation.error}")

        # 阶段 3：把观察结果合并回 Agent 状态。
        state = update_state_after_step(
            state=state,
            action=action,
            observation=observation,
        )

        # 阶段 4：组装完整步骤并持久化，便于之后复盘。
        step = RepoOpsStep(
            step_id=step_id,
            action=action,
            observation=observation,
            state_status=state.status,
        )
        append_trace(step)

        # Planner 成功选择 finish 后提前退出 for 循环。
        if state.status == "finished":
            break

    # 循环耗尽仍未 finish，说明 Agent 未能在步数预算内完成任务。
    if state.status != "finished":
        state.status = "failed"
        state.final_answer = (
            "Agent stopped because max_steps was reached before finish."
        )
        state.updated_at = now_iso()

    print("\n[FINAL STATE]")
    # model_dump_json() 将完整状态直接序列化成格式化 JSON。
    print(state.model_dump_json(indent=2))

    print(f"\n[TRACE LOG]")
    print(LOG_FILE)

    # 返回最终状态，方便未来由测试或其他 Python 模块调用并检查。
    return state


def main() -> None:
    """
    程序入口。
    """
    # 相邻字符串会被 Python 自动拼接，这里用括号实现跨行书写。
    user_goal = (
        "Inspect this RepoOps Assistant project, identify what files exist, "
        "read key documentation if available, and summarize the current project status."
    )

    # 启动 Agent，并限制最多执行 6 个“规划 + 工具”步骤。
    run_agent_loop(
        user_goal=user_goal,
        repo_path=REPO_ROOT,
        max_steps=6,
    )


# __name__ 是 Python 自动设置的模块名；直接运行时其值为 "__main__"。
if __name__ == "__main__":
    main()
