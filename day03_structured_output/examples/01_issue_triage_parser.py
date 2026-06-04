"""
Day03 示例：Issue triage 的结构化输出解析。

这份代码演示的不是“让模型回答一段话”，而是让模型输出一份可被程序处理的 JSON。
核心流程是：

1. 准备 Issue 信息和 prompt，要求 LLM 严格输出 JSON。
2. 调用模型，拿到原始文本 raw_text。
3. 从 raw_text 中提取 JSON，得到 raw_json。
4. 用 IssueTriageDecision.model_validate(raw_json) 做结构校验。
5. 校验通过后，得到稳定可用的 Pydantic 对象 decision。

Day03 最重要的学习点：
模型输出天然是不稳定的文本；structured output 的目标，是把它变成可验证、可落库、
可分支判断、可继续交给下游程序使用的数据。
"""

import os
import re
import sys
import json
import time
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from anthropic import Anthropic
from pydantic import ValidationError


# DAY_DIR 指向 day03_structured_output，用于定位 prompts、schemas、logs 等 day03 内部资源。
DAY_DIR = Path(__file__).resolve().parents[1] 
####parents 是从 0 开始编号的

# ROOT_DIR 指向 agent_learning 根目录；当前代码从根目录读取 .env。
ROOT_DIR = Path(__file__).resolve().parents[2]

# 将 day03_structured_output 加入模块搜索路径，方便导入 schemas 包。
sys.path.append(str(DAY_DIR))

#from schemas.issue_triage_schema import IssueTriageDecision
from schemas import IssueTriageDecision

load_dotenv(ROOT_DIR / ".env")

BASE_URL = os.getenv("LLM_BASE_URL")
API_KEY = os.getenv("LLM_API_KEY")
MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2048"))

if not BASE_URL:
    raise ValueError("未找到 LLM_BASE_URL，请检查根目录 .env。")

if not API_KEY:
    raise ValueError("未找到 LLM_API_KEY，请检查根目录 .env。")


# 当前示例仍使用 Anthropic 兼容 messages 接口。
# 如果后续切成 OpenAI 兼容接口，主要修改这里和 triage_issue() 里的 client.messages.create。
client = Anthropic(
    api_key=API_KEY,
    base_url=BASE_URL,
)


def save_log(record: dict) -> None:
    """把每次结构化输出实验记录到 JSONL，方便复盘模型原始输出和校验结果。"""

    log_dir = DAY_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "issue_triage_calls.jsonl"

    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def extract_text(response) -> str:
    """从 Anthropic 响应对象中抽取文本内容。"""

    texts = []

    for block in response.content:
        if getattr(block, "type", None) == "text":
            texts.append(block.text)

    return "\n".join(texts).strip()


def extract_json(text: str) -> dict:
    """
    从模型原始文本中提取 JSON。

    为什么需要这个函数：
    即使 prompt 要求“只输出 JSON”，模型有时仍可能输出 markdown 代码块、
    前后解释性文字，或者带 ```json 的格式。这个函数做了几层兜底提取。
    """

    text = text.strip()

    # 最理想情况：模型输出本身就是纯 JSON 字符串。
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 常见情况：模型把 JSON 包在 ```json ... ``` 代码块里。
    code_block = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        text,
        re.DOTALL,
    )
    if code_block:
        return json.loads(code_block.group(1))

    # 最后兜底：从文本中寻找第一个大括号包裹的 JSON 对象。
    json_block = re.search(r"\{.*\}", text, re.DOTALL)
    if json_block:
        return json.loads(json_block.group(0))

    raise ValueError("模型输出中没有找到有效 JSON。")


def build_user_prompt(issue_snapshot: dict) -> str:
    """
    构造用户 prompt。

    这里把 Issue 信息嵌入 prompt，并显式列出字段名和取值限制。
    注意：prompt 约束只是“提醒模型”，真正的硬校验在 Pydantic schema 中完成。
    """

    return f"""
请根据下面的 Issue 信息进行结构化分流判断。

Issue 信息：
{json.dumps(issue_snapshot, ensure_ascii=False, indent=2)}

请严格输出 JSON，不要输出 markdown，不要输出解释性文字。

JSON 字段必须包括：
- issue_type
- priority
- needs_more_info
- suggested_labels
- next_action
- assigned_role
- risk_level
- reason
- uncertainty

字段取值限制：

issue_type 只能是：
bug, feature, question, documentation, task, security, performance, unknown

priority 只能是：
low, medium, high, critical

next_action 只能是：
ask_for_reproduction, request_more_info, assign_to_maintainer,
create_fix_plan, add_to_backlog, close_as_duplicate,
escalate_security_review, no_action

assigned_role 只能是：
maintainer, developer, docs_writer, security_reviewer, qa_engineer, none

risk_level 只能是：
low, medium, high
"""


def triage_issue(issue_snapshot: dict) -> IssueTriageDecision:
    """
    对一个 Issue 做结构化分流，并返回已校验的 IssueTriageDecision 对象。

    这是 Day03 最关键的函数。重点看三行：
    raw_text = extract_text(response)
    raw_json = extract_json(raw_text)
    decision = IssueTriageDecision.model_validate(raw_json)
    """

    system_prompt = (
        "你是一个严谨的 Agentic RepoOps Assistant，负责对代码仓库 Issue "
        "进行结构化分流。你必须根据输入信息判断，不要编造仓库中不存在的事实。"
        "你必须严格输出 JSON。"
    )

    user_prompt = build_user_prompt(issue_snapshot)

    start_time = time.time()

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ],
        )

        # 第一步：把模型响应对象转换成原始文本。此时它仍然只是字符串，不可信。
        raw_text = extract_text(response)

        # 第二步：从原始文本中提取 JSON dict。此时字段和值还没有被 schema 校验。
        raw_json = extract_json(raw_text)

        # 第三步：用 Pydantic 校验 JSON 是否符合 IssueTriageDecision 的结构和取值限制。
        # 校验通过后，decision 就是可以稳定读取字段的 Python 对象。
        decision = IssueTriageDecision.model_validate(raw_json)

        elapsed = time.time() - start_time

        save_log(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "model": MODEL,
                "issue_snapshot": issue_snapshot,
                "raw_output": raw_text,
                "parsed_json": raw_json,
                "validated_decision": decision.model_dump(),
                "elapsed_seconds": round(elapsed, 3),
                "status": "success",
            }
        )

        return decision

    except (ValidationError, ValueError, json.JSONDecodeError) as e:
        # 这一类错误属于“结构化输出失败”：
        # 可能是模型没有输出 JSON、JSON 格式错误，或字段不符合 schema。
        elapsed = time.time() - start_time

        save_log(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "model": MODEL,
                "issue_snapshot": issue_snapshot,
                "error": str(e),
                "elapsed_seconds": round(elapsed, 3),
                "status": "validation_failed",
            }
        )

        raise

    except Exception as e:
        # 这一类错误属于普通调用失败，例如网络、鉴权、模型服务异常等。
        elapsed = time.time() - start_time

        save_log(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "model": MODEL,
                "issue_snapshot": issue_snapshot,
                "error": str(e),
                "elapsed_seconds": round(elapsed, 3),
                "status": "failed",
            }
        )

        raise


if __name__ == "__main__":
    # 这里构造一个模拟 GitHub Issue。真实项目中，这些信息可以来自 GitHub API 或数据库。

    # issue_snapshot = {
    #     "repo_name": "agentic-repoops-assistant",
    #     "repo_context": (
    #         "这是一个用于分析代码仓库、日志和 Issue 的 Agent 项目。"
    #         "当前已经实现了基础 LLM 调用和 prompt 模板，正在开发结构化输出能力。"
    #     ),
    #     "issue_title": "App crashes on Windows when loading .env file",
    #     "issue_body": (
    #         "When I run python app.py on Windows, the program crashes immediately. "
    #         "The traceback says ModuleNotFoundError: No module named 'dotenv'. "
    #         "I followed the README but it did not mention installing python-dotenv."
    #     ),
    #     "recent_errors": [
    #         "ModuleNotFoundError: No module named 'dotenv'",
    #         "File: app.py, line 6, from dotenv import load_dotenv",
    #     ],
    # }

        
    # issue_snapshot = {
    # "repo_name": "agentic-repoops-assistant",
    # "repo_context": "一个 Agent 项目。",
    # "issue_title": "It does not work",
    # "issue_body": "The app is broken. Please fix it.",
    # "recent_errors": [],
    # }


#     issue_snapshot = {
#     "repo_name": "agentic-repoops-assistant",
#     "repo_context": "一个 Agent 项目。",
#     "issue_title": "README missing installation steps",
#     "issue_body": "The README does not explain how to create .env or install dependencies.",
#     "recent_errors": [],
# }
    
    issue_snapshot = {
    "repo_name": "agentic-repoops-assistant",
    "repo_context": "一个 Agent 项目。",
    "issue_title": "API key may be logged in plain text",
    "issue_body": "The logs seem to include the full LLM_API_KEY value after a failed request.",
    "recent_errors": [
        "LLM_API_KEY=sk-xxxxxx was printed in logs"
    ],
}
    # 执行结构化分流：返回值不是字符串，而是 IssueTriageDecision 对象。
    decision = triage_issue(issue_snapshot)

    print("\nIssue 结构化分流结果：")
    print(json.dumps(decision.model_dump(), ensure_ascii=False, indent=2))
