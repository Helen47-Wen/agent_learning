import os  # 读取系统环境变量中的模型服务配置。
import json  # 将每次调用记录序列化为 JSONL。
import time  # 统计模型接口调用耗时。
from pathlib import Path  # 处理 .env、日志文件等路径。
from datetime import datetime  # 生成日志中的时间戳。

from dotenv import load_dotenv  # 加载项目根目录下的 .env 文件。
from openai import OpenAI  # 使用 OpenAI 兼容 chat completions 接口调用模型。


ROOT_DIR = Path(__file__).resolve().parent  # 当前文件在项目示例根目录下，parent 就是 .env 所在目录。
load_dotenv(ROOT_DIR / ".env")  # 将根目录 .env 中的变量加载到当前进程环境。

BASE_URL = os.getenv("LLM_BASE_URL")  # 模型服务基础地址，例如兼容 OpenAI API 的代理地址。
API_KEY = os.getenv("LLM_API_KEY")  # 模型服务 API Key。
MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")  # 模型名称；未配置时使用默认模型。
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))  # 最大输出 token 数；环境变量需转为整数。

if not BASE_URL:  # 缺少服务地址时，后续请求无法发送。
    raise ValueError("未找到 LLM_BASE_URL，请检查根目录 .env。")  # 提前抛出清晰的配置错误。
if not API_KEY:  # 缺少 API Key 时，后续请求无法鉴权。
    raise ValueError("未找到 LLM_API_KEY，请检查根目录 .env。")  # 提前抛出清晰的配置错误。


client = OpenAI(  # 创建 OpenAI 兼容客户端，后续实验复用该实例。
    api_key=API_KEY,  # 使用 .env 中读取到的 API Key。
    base_url=BASE_URL,  # 使用 .env 中读取到的模型服务地址。
)


def save_log(record: dict) -> None:  # 保存一次模型调用记录。
    log_dir = Path(__file__).resolve().parent / "logs"  # 日志目录放在当前脚本目录下的 logs 子目录。
    log_dir.mkdir(exist_ok=True)  # 如果日志目录不存在就创建；已存在则跳过。

    log_file = log_dir / "day02_messages_prompt_calls.jsonl"  # 每行保存一条 JSON 调用记录。

    with log_file.open("a", encoding="utf-8") as f:  # 以追加模式写入，保留历史实验记录。
        f.write(json.dumps(record, ensure_ascii=False) + "\n")  # ensure_ascii=False 让中文直接可读。


def build_openai_messages(system_prompt: str, messages: list[dict]) -> list[dict]:  # 组装 OpenAI chat 消息列表。
    if system_prompt:  # OpenAI 兼容接口把系统提示词放进 messages，而不是单独的 system 参数。
        return [{"role": "system", "content": system_prompt}, *messages]  # system 消息放在对话最前面。

    return messages  # 没有系统提示词时，直接使用原始 messages。


def extract_text(response) -> str:  # 从 OpenAI chat completions 响应对象中提取文本内容。
    if not response.choices:  # 兼容异常情况：响应中没有候选结果。
        return ""  # 没有 choices 时返回空字符串。

    content = response.choices[0].message.content  # 读取第一个候选回答的消息内容。
    return content or ""  # content 可能为 None，因此兜底为空字符串。


def call_llm(system_prompt: str, messages: list[dict]) -> str:  # 统一调用模型并返回文本回答。
    start_time = time.time()  # 记录请求开始时间，用于计算耗时。
    openai_messages = build_openai_messages(system_prompt, messages)  # 将 system_prompt 合并进 OpenAI 消息列表。

    try:  # 成功时记录输出日志，失败时记录错误日志。
        response = client.chat.completions.create(  # 调用 OpenAI 兼容 chat completions API。
            model=MODEL,  # 指定本次请求使用的模型。
            max_tokens=MAX_TOKENS,  # 限制本次请求的最大输出长度。
            messages=openai_messages,  # 传入包含 system/user/assistant 的完整消息列表。
        )

        output_text = extract_text(response)  # 将响应对象转换成纯文本。
        elapsed = time.time() - start_time  # 计算本次调用耗时。

        save_log(  # 写入成功调用日志，便于复现实验。
            {
                "time": datetime.now().isoformat(timespec="seconds"),  # 当前本地时间，精确到秒。
                "model": MODEL,  # 记录使用的模型名称。
                "system_prompt": system_prompt,  # 记录系统提示词。
                "messages": messages,  # 记录原始对话消息。
                "openai_messages": openai_messages,  # 记录实际发送给 OpenAI 兼容接口的消息。
                "output": output_text,  # 记录模型输出。
                "elapsed_seconds": round(elapsed, 3),  # 记录耗时并保留 3 位小数。
                "status": "success",  # 标记本次调用成功。
            }
        )

        return output_text  # 将模型文本回答返回给调用方。

    except Exception as e:  # 捕获调用失败、解析失败或写日志失败等异常。
        elapsed = time.time() - start_time  # 失败时也记录已经消耗的时间。

        save_log(  # 写入失败调用日志，便于排查问题。
            {
                "time": datetime.now().isoformat(timespec="seconds"),  # 当前本地时间，精确到秒。
                "model": MODEL,  # 记录准备调用的模型名称。
                "system_prompt": system_prompt,  # 记录失败请求的系统提示词。
                "messages": messages,  # 记录失败请求的原始对话消息。
                "openai_messages": openai_messages,  # 记录失败时实际发送的消息格式。
                "error": str(e),  # 记录异常文本。
                "elapsed_seconds": round(elapsed, 3),  # 记录失败前耗时。
                "status": "failed",  # 标记本次调用失败。
            }
        )

        raise  # 重新抛出异常，让主程序显示真实错误。


def run_experiment(title: str, system_prompt: str, messages: list[dict]) -> None:  # 运行一组 prompt/messages 实验。
    print("\n" + "=" * 80)  # 打印实验分隔线。
    print(title)  # 打印实验标题。
    print("=" * 80)  # 打印标题下方分隔线。

    answer = call_llm(system_prompt=system_prompt, messages=messages)  # 调用模型获取本实验回答。

    print("\n模型回答：")  # 标注下面输出来自模型。
    print(answer)  # 在终端打印模型回答。


if __name__ == "__main__":  # 只有直接运行该文件时才执行实验。
    # 实验 1：不提供明确 system prompt，观察模型默认回答方式。
    run_experiment(
        title="实验 1：无明确 system prompt",  # 当前实验标题。
        system_prompt="",  # 空系统提示词表示不额外设定角色或风格。
        messages=[  # 当前实验的对话消息。
            {
                "role": "user",  # 用户消息。
                "content": "请解释 LLM 和 Agent 的区别。",  # 基准问题，用于和后续实验对比。
            }
        ],
    )

    # 实验 2：面向初学者讲解，观察 system prompt 对表达风格的影响。
    run_experiment(
        title="实验 2：初学者讲解型 system prompt",  # 当前实验标题。
        system_prompt=(  # 系统提示词会被两段字符串自动拼接。
            "你是一个面向初学者的 AI Agent 讲师。"  # 设定模型身份。
            "回答要通俗、简洁，尽量使用类比。"  # 设定回答风格。
        ),
        messages=[  # 当前实验的对话消息。
            {
                "role": "user",  # 用户消息。
                "content": "请解释 LLM 和 Agent 的区别。",  # 与实验 1 保持同题。
            }
        ],
    )

    # 实验 3：面向工程师讲解，观察 system prompt 对技术深度的影响。
    run_experiment(
        title="实验 3：工程师型 system prompt",  # 当前实验标题。
        system_prompt=(  # 系统提示词会被两段字符串自动拼接。
            "你是一个严谨的 AI Agent 工程师。"  # 设定模型身份。
            "回答时要强调系统架构、状态管理、工具调用、异常处理和可评估性。"  # 设定技术关注点。
        ),
        messages=[  # 当前实验的对话消息。
            {
                "role": "user",  # 用户消息。
                "content": "请解释 LLM 和 Agent 的区别。",  # 与前两个实验保持同题。
            }
        ],
    )

    # 实验 4：加入 AUV / Fluent 项目背景，观察领域上下文的影响。
    run_experiment(
        title="实验 4：结合 AUV / Fluent 自动化项目",  # 当前实验标题。
        system_prompt=(  # 系统提示词会被三段字符串自动拼接。
            "你是一个 AI Agent 工程顾问。"  # 设定模型身份。
            "用户正在做 SolidWorks 到 Fluent 的自动化仿真项目。"  # 提供工程项目背景。
            "你需要把 Agent 概念映射到 CAD/CAE 工程自动化场景中。"  # 要求回答贴合 CAD/CAE 自动化。
        ),
        messages=[  # 当前实验的对话消息。
            {
                "role": "user",  # 用户消息。
                "content": (  # 较长问题分成两段字符串自动拼接。
                    "我已经有 SolidWorks、SpaceClaim、Fluent Meshing、Fluent Solver "  # 列出现有自动化工具链。
                    "的自动化脚本。请说明为什么还需要 Agent，而不只是普通脚本。"  # 询问 Agent 相比脚本的价值。
                ),
            }
        ],
    )

    # 实验 5：使用多轮 messages，观察上下文继承和 Agent State 讨论。
    run_experiment(
        title="实验 5：多轮 messages，观察上下文继承",  # 当前实验标题。
        system_prompt=(  # 系统提示词会被两段字符串自动拼接。
            "你是一个 AI Agent 工程学习助手。"  # 设定模型身份。
            "回答要结合工程自动化项目。"  # 要求回答结合项目语境。
        ),
        messages=[  # 多轮消息模拟已有对话上下文。
            {
                "role": "user",  # 第一轮用户消息。
                "content": "我正在做 AUV 外流场自动化仿真。",  # 提供 AUV 仿真任务背景。
            },
            {
                "role": "assistant",  # 第一轮助手消息。
                "content": (  # 模拟助手之前已经给出的流程拆解。
                    "这个流程可以拆成 SolidWorks 参数修改、SpaceClaim 外流域生成、"  # CAD 与几何处理阶段。
                    "Fluent Meshing 网格划分、Fluent Solver 求解和结果报告生成。"  # 网格、求解与报告阶段。
                ),
            },
            {
                "role": "user",  # 第二轮用户消息。
                "content": "那这里面的 Agent State 应该保存哪些信息？",  # 基于前文追问状态设计。
            },
        ],
    )
