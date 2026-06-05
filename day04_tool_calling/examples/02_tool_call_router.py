"""
工具调用路由示例。

完整流程：
1. 把用户目标和可用工具说明发送给大模型。
2. 从模型回复中提取 JSON，并校验为 ToolCallDecision。
3. 根据 tool_name 调用对应的本地只读工具。
4. 保存模型决策、工具结果和耗时日志。
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

# __file__ 是当前脚本路径；parents[1] 表示上两级 day04_tool_calling 目录，
# parents[2] 表示再上一级的项目根目录 agent_learning。
DAY_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = Path(__file__).resolve().parents[2]

# sys.path 决定 Python 去哪些目录查找模块。加入 DAY_DIR 后，下面才能导入 schemas 和 tools。
sys.path.append(str(DAY_DIR))

from schemas.tool_call_schema import ToolCallDecision
from tools.file_tools import list_project_files, read_text_file, search_text, read_recent_log


# 从项目根目录的 .env 文件加载环境变量。
load_dotenv(ROOT_DIR / ".env")

# os.getenv("名称") 读取环境变量；
# 第二个参数是环境变量不存在时使用的默认值。
BASE_URL = os.getenv("LLM_BASE_URL")
API_KEY = os.getenv("LLM_API_KEY")
MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")
# 环境变量读出来都是字符串，因此 token 数量需要用 int() 转成整数。
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2048"))

if not BASE_URL:
    raise ValueError("未找到 LLM_BASE_URL，请检查根目录 .env。")

if not API_KEY:
    raise ValueError("未找到 LLM_API_KEY，请检查根目录 .env。")


client = Anthropic(
    api_key=API_KEY,
    base_url=BASE_URL,
)


def save_log(record: dict) -> None:
    """把一次工具调用记录追加到 JSON Lines 日志文件中。"""
    log_dir = DAY_DIR / "logs"
    # exist_ok=True 表示目录已存在时不报错。
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "tool_call_router.jsonl"

    # 以追加模式打开日志文件，把 record 转换成保留中文的 JSON 字符串，写到文件末尾，然后换行。
    # "a" 是追加模式；with 代码块结束后会自动关闭文件。
    with log_file.open("a", encoding="utf-8") as f:
        # ensure_ascii=False 保留中文；每条 JSON 后写入换行，形成一行一条记录的 JSONL。
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def extract_text(response) -> str:
    """从 Anthropic 响应的多个内容块中提取并拼接文本。"""
    texts = []
    for block in response.content:
        # getattr(obj, "type", None) 安全读取属性；属性不存在时返回 None。
        if getattr(block, "type", None) == "text":
            texts.append(block.text)
    # "\n".join(...) 用换行连接列表中的字符串，strip() 去掉首尾空白。
    return "\n".join(texts).strip()


def extract_json(text: str) -> dict:
    """从纯 JSON、Markdown JSON 代码块或混合文本中提取 JSON 对象。"""
    text = text.strip()

    try:
        # 优先按完整 JSON 解析，这是最严格、最可靠的情况。
        return json.loads(text)
    except json.JSONDecodeError:
        # pass 表示捕获解析错误后暂不处理，继续尝试后面的兼容方案。
        pass

    # r"..." 是原始字符串，适合书写正则；re.DOTALL 让 . 也能匹配换行符。
    # (\{.*?\}) 是捕获组：寻找代码块中的 JSON 对象，*? 表示非贪婪匹配。
    code_block = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        text,
        re.DOTALL,
    )
    if code_block:
        # group(1) 取得正则中第一对圆括号捕获到的内容。
        return json.loads(code_block.group(1))

    # 如果模型在 JSON 前后添加了解释文字，再尝试提取最外层的 {...}。
    json_block = re.search(r"\{.*\}", text, re.DOTALL)
    if json_block:
        # group(0) 表示整个正则表达式匹配到的文本。
        return json.loads(json_block.group(0))

    raise ValueError("模型输出中未找到有效 JSON。")


def build_tool_selection_prompt(user_goal: str, project_root: str) -> str:
    """构造工具选择提示词，把运行时参数插入模板。"""
    # f"""...""" 是多行格式化字符串，其中 {变量名} 会替换成变量的实际值。
    # 提示词中的 {{}} 使用双花括号，是为了在 f-string 中输出字面量 {}。
    return f"""
你是 Agentic RepoOps Assistant 的工具路由器。

用户目标：
{user_goal}

项目根目录：
{project_root}

可用工具：

1. list_project_files
用途：列出项目中的文件。
参数：
- project_root: string
- max_files: integer，可选

2. read_text_file
用途：读取项目中的文本文件，例如 README.md。
参数：
- project_root: string
- relative_path: string
- max_chars: integer，可选

3. search_text
用途：在项目文本文件中搜索关键词。
参数：
- project_root: string
- keyword: string
- max_matches: integer，可选

4. read_recent_log
用途：读取日志文件最后若干行。
参数：
- project_root: string
- relative_path: string
- n_lines: integer，可选

5. no_tool
用途：当不需要工具时使用。
参数：{{}}

请你判断应该调用哪个工具，并严格输出 JSON，不要输出 markdown，不要输出解释性文字。

JSON 字段：
- thought
- tool_name
- tool_args
- risk_level
- need_human_review
- reason

tool_name 只能是：
list_project_files, read_text_file, search_text, read_recent_log, no_tool

注意：
- 今天只允许 low 风险的只读工具。
- 不要请求删除、覆盖、修改、执行命令等操作。
- 如果只是检查项目有哪些文件，优先使用 list_project_files。
- 如果要看 README 内容，使用 read_text_file。
"""


def choose_tool(user_goal: str, project_root: str) -> ToolCallDecision:
    """调用大模型选择工具，并把模型输出校验为结构化决策。"""
    system_prompt = (
        # 相邻字符串字面量会被 Python 自动拼接成一个字符串。
        "你是一个严格的工具调用路由器。"
        "你只能根据给定工具选择下一步，不允许编造工具名称。"
        "你必须严格输出 JSON。"
    )

    prompt = build_tool_selection_prompt(user_goal, project_root)

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        # messages 是消息列表，每条消息用字典表示角色和内容。
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = extract_text(response)
    raw_json = extract_json(raw_text)

    # Pydantic 会检查字段是否齐全、类型是否正确，以及 tool_name 是否为允许的值。
    return ToolCallDecision.model_validate(raw_json)


def dispatch_tool(decision: ToolCallDecision):
    """根据结构化决策分发并执行对应工具。"""
    tool_name = decision.tool_name
    args = decision.tool_args

    if decision.need_human_review:
        return {
            "status": "blocked",
            "message": "该工具调用需要人工确认，当前未执行。",
            "decision": decision.model_dump(),
        }

    if tool_name == "list_project_files":
        # **args 把字典解包为关键字参数，例如 {"max_files": 10} -> max_files=10。
        # model_dump() 再把 Pydantic 返回对象转换为普通字典，方便记录和打印。
        return list_project_files(**args).model_dump()

    if tool_name == "read_text_file":
        return read_text_file(**args).model_dump()

    if tool_name == "search_text":
        return search_text(**args).model_dump()

    if tool_name == "read_recent_log":
        return read_recent_log(**args).model_dump()

    if tool_name == "no_tool":
        return {
            "status": "success",
            "message": "模型判断当前不需要调用工具。",
            "decision": decision.model_dump(),
        }

    return {
        "status": "failed",
        "message": f"未知工具：{tool_name}",
        "decision": decision.model_dump(),
    }


# 只有直接运行此脚本时该条件才成立；被其他文件 import 时不会执行下面的演示代码。
if __name__ == "__main__":
    project_root = str(ROOT_DIR / "projects" / "agentic_repoops_assistant")

    user_goal = "请检查 Agentic RepoOps Assistant 项目目前有哪些文件，判断 README 是否已经存在。"

    start = time.time()

    # 先由模型做工具选择，再由本地代码执行，模型本身不会直接操作文件。
    decision = choose_tool(user_goal=user_goal, project_root=project_root)
    tool_result = dispatch_tool(decision)

    record = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "user_goal": user_goal,
        "tool_decision": decision.model_dump(),
        "tool_result": tool_result,
        # time.time() 返回时间戳，两次相减得到运行耗时。
        "elapsed_seconds": round(time.time() - start, 3),
    }

    save_log(record)

    print("\n模型选择的工具：")
    print(json.dumps(decision.model_dump(), ensure_ascii=False, indent=2))

    print("\n工具执行结果：")
    print(json.dumps(tool_result, ensure_ascii=False, indent=2))
