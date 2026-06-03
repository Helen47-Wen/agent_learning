# 导入操作系统接口模块，用于读取环境变量
import os
# 导入时间模块，用于计算 API 调用耗时
import time
# 导入 JSON 模块，用于序列化日志记录
import json
# 导入路径处理模块，用于创建日志目录和文件
from pathlib import Path
# 导入日期时间模块，用于记录调用时间戳
from datetime import datetime

# 导入 python-dotenv 库，用于从 .env 文件加载环境变量
from dotenv import load_dotenv
# 导入 OpenAI SDK，用于调用兼容 OpenAI 接口的 LLM API
from openai import OpenAI


# ============== 1. 加载环境变量 ==============
# 从项目根目录的 .env 文件读取配置（API Key、Base URL、Model 等）
# 这样可以避免将敏感信息硬编码在代码中
load_dotenv()


# ============== 2. 读取环境变量 ==============
# 从环境变量中获取 API 密钥，用于身份验证
API_KEY = os.getenv("LLM_API_KEY")
# 从环境变量中获取 API 基础 URL，指向 LLM 服务的端点
BASE_URL = os.getenv("LLM_BASE_URL")
# 从环境变量中获取模型名称，默认使用 deepseek-v4-flash
MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")


# ============== 3. 基本检查 ==============
# 如果没有配置 API 密钥，抛出异常提示用户检查 .env 文件
# 这是一种防御性编程，避免运行时出现更难调试的错误
if not API_KEY:
    raise ValueError(
        "未找到 OPENAI_API_KEY。请检查 .env 文件中是否已正确配置 OPENAI_API_KEY。"
    )


# ============== 4. 初始化客户端 ==============
# 创建 OpenAI 客户端实例
# - api_key: 用于 API 身份验证
# - base_url: 指定 API 端点（支持 DeepSeek 等兼容 OpenAI 接口的服务）
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


def save_log(record: dict) -> None:
    """
    把每次模型调用记录保存到 logs/llm_calls.jsonl。
    jsonl 的意思是：每一行都是一个独立 JSON。

    用途：
    - 记录每次 API 调用的输入、输出、耗时等信息
    - 便于后续分析、调试和审计
    """
    # 创建日志目录（如果不存在）
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # 定义日志文件路径
    log_file = log_dir / "llm_calls.jsonl"

    # 以追加模式打开文件，将记录写入新的一行
    # ensure_ascii=False 确保中文字符正常显示，而不是被转义
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def call_llm(user_input: str) -> str:
    """
    最小 LLM 调用函数。
    输入一段用户文本，返回模型回答。

    参数:
        user_input: 用户输入的问题或指令

    返回:
        模型生成的回答文本

    异常:
        如果 API 调用失败，会记录错误日志并重新抛出异常
    """
    # 记录开始时间，用于计算耗时
    start_time = time.time()

    try:
        # 调用 Chat Completions API
        # - model: 指定使用的模型
        # - messages: 消息数组，包含系统提示和用户输入
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    # system 角色：定义 AI 的行为和人设
                    "role": "system",
                    "content": (
                        "你是一个面向初学者的 AI Agent 工程讲师。"
                        "回答时必须使用简洁中文，并尽量结合工程项目举例。"
                    ),
                },
                {
                    # user 角色：用户的实际输入
                    "role": "user",
                    "content": user_input,
                },
            ],
        )

        # 从响应中提取模型生成的文本
        # choices[0] 获取第一个（也是唯一的）生成结果
        # .message.content 获取消息内容
        output_text = response.choices[0].message.content

        # 计算 API 调用耗时
        elapsed = time.time() - start_time

        # 记录成功的调用日志
        save_log(
            {
                "time": datetime.now().isoformat(timespec="seconds"),  # 时间戳（秒精度）
                "model": MODEL,           # 使用的模型
                "user_input": user_input,  # 用户输入
                "output": output_text,     # 模型输出
                "elapsed_seconds": round(elapsed, 3),  # 耗时（保留3位小数）
                "status": "success",       # 状态标记
            }
        )

        # 返回模型回答
        return output_text

    except Exception as e:
        # 如果发生异常，计算耗时并记录错误日志
        elapsed = time.time() - start_time

        # 记录失败的调用日志
        save_log(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "model": MODEL,
                "user_input": user_input,
                "error": str(e),  # 记录错误信息
                "elapsed_seconds": round(elapsed, 3),
                "status": "failed",  # 状态标记为失败
            }
        )

        # 重新抛出异常，让调用者处理
        raise


# ============== 主程序入口 ==============
# 当直接运行此脚本时执行（而不是被导入时）
if __name__ == "__main__":
    # 定义测试问题
    question = "请用一句话解释什么是 AI Agent。"

    # 调用 LLM 获取回答
    answer = call_llm(question)

    # 打印结果
    print("\n模型回答：")
    print(answer)
