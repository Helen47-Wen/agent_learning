from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError


# ============================================================
# 1. 基础配置
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_DIR
LOG_DIR = PROJECT_DIR / "logs"
LOG_FILE = LOG_DIR / "repoops_v0_trace.jsonl"


def now_iso() -> str:
    """
    返回当前时间字符串，用于日志和状态更新时间。
    """
    return datetime.now().isoformat(timespec="seconds")


# ============================================================
# 2. Schema：Action / Observation / State / Step
# ============================================================

ActionName = Literal[
    "list_project_files",
    "read_text_file",
    "search_text",
    "finish",
]


class ActionArgs(BaseModel):
    """
    工具参数。

    不同工具会使用不同字段：
    - list_project_files 使用 root / max_files
    - read_text_file 使用 path / max_chars
    - search_text 使用 root / query / max_matches
    """

    root: str | None = None
    path: str | None = None
    query: str | None = None
    max_files: int = 50
    max_chars: int = 3000
    max_matches: int = 20


class ReactAction(BaseModel):
    """
    大模型 Planner 输出的结构化动作。

    注意：
    模型只负责“决定要做什么”；
    Python 才负责真正执行。
    """

    action_name: ActionName = Field(description="The next tool/action to execute.")
    action_args: ActionArgs = Field(default_factory=ActionArgs)
    reason: str = Field(description="A short reason for choosing this action.")


class RepoOpsObservation(BaseModel):
    """
    工具执行后的观察结果。
    """

    tool_name: str
    success: bool
    data: Any | None = None
    error: str | None = None
    created_at: str = Field(default_factory=now_iso)


class RepoOpsState(BaseModel):
    """
    RepoOps Assistant v0 的内部状态。
    """

    run_id: str
    user_goal: str
    repo_path: str
    observations: list[RepoOpsObservation] = Field(default_factory=list)
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
    base = Path(repo_path).resolve()
    target = Path(user_path)

    if not target.is_absolute():
        target = base / target

    target = target.resolve()

    if target != base and base not in target.parents:
        raise ValueError(f"Path is outside repo: {target}")

    return target


# ============================================================
# 4. 工具函数：只读文件工具
# ============================================================

def list_project_files(repo_path: str, root: str | None = None, max_files: int = 50) -> list[str]:
    """
    列出项目文件。
    """
    base = Path(repo_path).resolve()

    if root:
        root_path = resolve_inside_repo(repo_path, root)
    else:
        root_path = base

    results: list[str] = []

    for path in root_path.rglob("*"):
        if not path.is_file():
            continue

        rel_path = path.relative_to(base).as_posix()

        if ".git" in rel_path or "__pycache__" in rel_path:
            continue

        results.append(rel_path)

        if len(results) >= max_files:
            break

    return results


def read_text_file(repo_path: str, path: str, max_chars: int = 3000) -> str:
    """
    读取文本文件。
    """
    file_path = resolve_inside_repo(repo_path, path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

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
    base = Path(repo_path).resolve()

    if root:
        root_path = resolve_inside_repo(repo_path, root)
    else:
        root_path = base

    matches: list[dict[str, str]] = []

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

    for path in root_path.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in allowed_suffixes:
            continue

        rel_path = path.relative_to(base).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")

        if query.lower() in text.lower():
            matches.append(
                {
                    "file": rel_path,
                    "query": query,
                }
            )

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
    try:
        args = action.action_args

        if action.action_name == "list_project_files":
            data = list_project_files(
                repo_path=state.repo_path,
                root=args.root,
                max_files=args.max_files,
            )
            return RepoOpsObservation(
                tool_name=action.action_name,
                success=True,
                data=data,
            )

        if action.action_name == "read_text_file":
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
            return RepoOpsObservation(
                tool_name=action.action_name,
                success=True,
                data={
                    "message": "RepoOps Assistant v0 finished.",
                    "reason": action.reason,
                },
            )

        raise ValueError(f"Unknown action: {action.action_name}")

    except Exception as exc:
        return RepoOpsObservation(
            tool_name=action.action_name,
            success=False,
            error=str(exc),
        )


# ============================================================
# 6. LLM Planner
# ============================================================

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
"""


def build_client() -> OpenAI:
    """
    初始化 OpenAI SDK 客户端。

    支持：
    - 官方 OpenAI API
    - 部分 OpenAI-compatible API
    """
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")

    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in .env")

    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)

    return OpenAI(api_key=api_key)


def compact_observation(obs: RepoOpsObservation, max_chars: int = 1200) -> dict[str, Any]:
    """
    压缩 Observation，避免把太长的文件内容全部塞回模型上下文。
    """
    data_text = json.dumps(obs.data, ensure_ascii=False)

    if len(data_text) > max_chars:
        data_text = data_text[:max_chars] + "...[truncated]"

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
    payload = {
        "user_goal": state.user_goal,
        "repo_path": state.repo_path,
        "status": state.status,
        "risk_level": state.risk_level,
        "need_human_review": state.need_human_review,
        "observations": [
            compact_observation(obs)
            for obs in state.observations[-5:]
        ],
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

    return json.dumps(payload, ensure_ascii=False, indent=2)


def plan_next_action(client: OpenAI, model: str, state: RepoOpsState) -> ReactAction:
    """
    让大模型基于当前 State 选择下一步动作。

    优先使用 Responses API + Pydantic structured output。
    如果当前模型或兼容 API 不支持，则回退到 Chat Completions JSON 模式。
    """
    planner_input = build_planner_input(state)

    try:
        response = client.responses.parse(
            model=model,
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
            text_format=ReactAction,
        )

        return response.output_parsed

    except Exception as responses_error:
        print("[WARN] Responses structured output failed, fallback to chat JSON mode.")
        print(f"[WARN] {responses_error}")

        schema_hint = ReactAction.model_json_schema()

        completion = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
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
            response_format={"type": "json_object"},
        )

        content = completion.choices[0].message.content or "{}"

        try:
            return ReactAction.model_validate_json(content)
        except ValidationError as validation_error:
            raise RuntimeError(
                "Model returned invalid ReactAction JSON."
            ) from validation_error


# ============================================================
# 7. 日志与主循环
# ============================================================

def append_trace(step: RepoOpsStep) -> None:
    """
    追加一行 jsonl trace。
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(
                step.model_dump(),
                ensure_ascii=False,
            )
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
    state.observations.append(observation)
    state.next_action_reason = action.reason
    state.updated_at = now_iso()

    if not observation.success:
        state.risk_level = "medium"

    if action.action_name == "finish" and observation.success:
        state.status = "finished"
        state.final_answer = action.reason

    return state


def run_agent_loop(user_goal: str, repo_path: Path, max_steps: int = 6) -> RepoOpsState:
    """
    运行 RepoOps Assistant v0。
    """
    client = build_client()
    model = os.getenv("OPENAI_MODEL", "gpt-5.5")

    state = RepoOpsState(
        run_id=f"repoops_v0_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        user_goal=user_goal,
        repo_path=str(repo_path.resolve()),
    )

    print("[INFO] RepoOps Assistant v0 started.")
    print(f"[INFO] Model: {model}")
    print(f"[INFO] Repo path: {state.repo_path}")

    for step_id in range(1, max_steps + 1):
        print(f"\n[STEP {step_id}] Planning next action...")

        action = plan_next_action(
            client=client,
            model=model,
            state=state,
        )

        print(f"[ACTION] {action.action_name}")
        print(f"[REASON] {action.reason}")

        observation = run_tool(
            state=state,
            action=action,
        )

        print(f"[OBSERVATION] success={observation.success}")

        if observation.error:
            print(f"[ERROR] {observation.error}")

        state = update_state_after_step(
            state=state,
            action=action,
            observation=observation,
        )

        step = RepoOpsStep(
            step_id=step_id,
            action=action,
            observation=observation,
            state_status=state.status,
        )
        append_trace(step)

        if state.status == "finished":
            break

    if state.status != "finished":
        state.status = "failed"
        state.final_answer = (
            "Agent stopped because max_steps was reached before finish."
        )
        state.updated_at = now_iso()

    print("\n[FINAL STATE]")
    print(state.model_dump_json(indent=2))

    print(f"\n[TRACE LOG]")
    print(LOG_FILE)

    return state


def main() -> None:
    """
    程序入口。
    """
    user_goal = (
        "Inspect this RepoOps Assistant project, identify what files exist, "
        "read key documentation if available, and summarize the current project status."
    )

    run_agent_loop(
        user_goal=user_goal,
        repo_path=REPO_ROOT,
        max_steps=6,
    )


if __name__ == "__main__":
    main()