"""RepoOps Assistant 的最小 RAG 问答应用。

核心流程：检查本地索引 → 检索 top_k 文本块 → 组装提示词
→ 调用聊天模型生成答案 → 将问题、来源与答案追加到 JSONL 日志。

本文件负责串联问答流程；索引构建、向量化和相似度计算位于 ``rag_index.py``。
语法与实现重点已标注在对应代码附近。
"""

# 延迟解析类型注解；类型注解用于静态提示，不会自动校验运行时数据。
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

# 导入索引模块暴露的路径常量和核心能力，避免在应用层重复实现检索逻辑。
from rag_index import INDEX_PATH, PROJECT_DIR, build_rag_index, retrieve_chunks


# Path 使用 / 运算符拼接路径，比手工处理不同系统的路径分隔符更安全。
LOG_DIR = PROJECT_DIR / "logs"
QA_LOG_PATH = LOG_DIR / "repoops_rag_v0_qa.jsonl"


# 三引号字符串适合保存跨多行的系统提示词。
RAG_SYSTEM_PROMPT = """
你是 RepoOps Assistant 的 RAG 问答模块。

你必须遵守：
1. 只能基于检索到的项目资料回答。
2. 不要编造项目中不存在的文件、模块或能力。
3. 如果资料不足，要明确说“当前检索资料不足”。
4. 回答时尽量引用 source_path，说明依据来自哪个文件。
5. 用中文回答，结构清晰。
"""


def now_iso() -> str:
    """生成精确到秒的本地 ISO 时间字符串，用作日志时间戳。"""
    # 链式调用：now() 创建时间对象，isoformat() 再把它格式化为字符串。
    return datetime.now().isoformat(timespec="seconds")


def build_chat_client() -> OpenAI:
    """
    从环境变量读取 API 配置并初始化聊天模型客户端。

    ``base_url`` 可选：配置后可以连接 DeepSeek 等兼容 OpenAI SDK 的服务。
    """
    # load_dotenv() 把 .env 中的配置加载到进程环境变量。
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")

    # 缺少密钥时尽早抛出明确错误，避免等到网络请求阶段才失败。
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in .env")

    # 有自定义地址时使用它；否则使用 SDK 默认的 OpenAI API 地址。
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)

    return OpenAI(api_key=api_key)


def ensure_index_exists() -> None:
    """
    如果索引不存在，就先构建索引。

    返回类型 ``None`` 表示函数只执行检查或构建操作，不返回业务数据。
    注意：这里仅检查“是否存在”，不会判断源文件更新后索引是否过期。
    """
    # exists() 是快速路径：已有索引时提前 return，避免重复执行昂贵的向量化。
    if INDEX_PATH.exists():
        print(f"[INFO] Existing RAG index found: {INDEX_PATH}")
        return

    print("[INFO] RAG index not found. Building index first...")
    build_rag_index(
        project_dir=PROJECT_DIR,
        index_path=INDEX_PATH,
    )


def format_context(chunks: list[dict[str, Any]]) -> str:
    """
    把检索结果整理成大模型上下文。

    ``list[dict[str, Any]]`` 表示字典列表；每个字典是一条检索到的文本块。
    """
    blocks: list[str] = []

    # enumerate(..., start=1) 同时取得序号和文本块，并让展示编号从 1 开始。
    for index, chunk in enumerate(chunks, start=1):
        # "\n".join(...) 将多行字段拼成一个字符串；:.4f 将分数显示为四位小数。
        block = "\n".join(
            [
                f"[资料 {index}]",
                f"source_path: {chunk['source_path']}",
                f"chunk_id: {chunk['chunk_id']}",
                f"score: {chunk['score']:.4f}",
                "content:",
                chunk["text"],
            ]
        )
        blocks.append(block)

    # 再用分隔线连接所有资料块，形成最终检索上下文。
    return "\n\n---\n\n".join(blocks)


def answer_with_rag(
    question: str,
    chunks: list[dict[str, Any]],
) -> str:
    """
    将用户问题和检索结果交给聊天模型，生成基于资料的回答。

    系统消息负责约束回答行为，用户消息同时携带问题与检索上下文。
    """
    load_dotenv()

    model = os.getenv("OPENAI_MODEL", "gpt-5.5")
    client = build_chat_client()
    context = format_context(chunks)

    # f-string 允许把 question 和 context 直接插入多行提示词。
    user_prompt = f"""
用户问题：
{question}

检索到的项目资料：
{context}

请基于以上资料回答。
"""

    # 使用 Chat Completions 接口；messages 按 system → user 的顺序传入。
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": RAG_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    )

    # API 返回候选列表，这里取第一个答案；or "" 防止 content 为 None。
    return completion.choices[0].message.content or ""


def append_qa_log(
    question: str,
    chunks: list[dict[str, Any]],
    answer: str,
) -> None:
    """
    将一次 RAG 问答以单行 JSON 追加到日志。

    日志保留检索来源、原始 score 和字符范围，方便复盘检索质量。
    """
    # parents=True 递归创建父目录；exist_ok=True 表示目录已存在时不报错。
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    record = {
        "created_at": now_iso(),
        "question": question,
        # 列表推导式：遍历 chunks，并为每个 chunk 生成一条精简的来源记录。
        "sources": [
            {
                "source_path": chunk["source_path"],
                "chunk_id": chunk["chunk_id"],
                "score": chunk["score"],
                "start_char": chunk["start_char"],
                "end_char": chunk["end_char"],
            }
            for chunk in chunks
        ],
        "answer": answer,
    }

    # "a" 是追加模式，不覆盖旧日志；with 会在结束或异常时自动关闭文件。
    with QA_LOG_PATH.open("a", encoding="utf-8") as file:
        # ensure_ascii=False 保留中文；末尾换行使每次记录成为独立 JSONL 行。
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_rag_qa(question: str, top_k: int = 5) -> str:
    """
    编排一次完整的 RepoOps RAG 问答，并返回最终答案。

    ``top_k`` 是默认参数，调用方未传值时检索最相关的 5 个文本块。
    """
    ensure_index_exists()

    print("\n[QUESTION]")
    print(question)

    print("\n[INFO] Retrieving chunks...")
    # 检索阶段会将问题向量化、计算相似度并返回得分最高的 top_k 条。
    chunks = retrieve_chunks(
        question=question,
        top_k=top_k,
        index_path=INDEX_PATH,
    )

    print("\n[RETRIEVED CHUNKS]")
    for chunk in chunks:
        print(
            f"- {chunk['source_path']} "
            f"| {chunk['chunk_id']} "
            f"| score={chunk['score']:.4f}"
        )

    # 生成阶段只把已检索的 chunks 作为项目资料提供给聊天模型。
    answer = answer_with_rag(
        question=question,
        chunks=chunks,
    )

    # 在答案成功生成后再写日志，保存完整的“问题—证据—答案”链路。
    append_qa_log(
        question=question,
        chunks=chunks,
        answer=answer,
    )

    print("\n[ANSWER]")
    print(answer)

    print("\n[QA LOG]")
    print(QA_LOG_PATH)

    return answer


def main() -> None:
    """解析命令行问题；未提供参数时使用内置的示例问题。"""
    # sys.argv[0] 是脚本名，真正的命令行参数从 sys.argv[1] 开始。
    if len(sys.argv) > 1:
        # 将多个命令行参数重新拼接为一个完整问题。
        question = " ".join(sys.argv[1:])
    else:
        # 相邻字符串字面量会被 Python 自动拼接成一个字符串。
        question = (
            "RepoOps Assistant v0 目前实现了哪些能力？"
            "它和 Day 08 的 RAG 有什么关系？"
        )

    run_rag_qa(
        question=question,
        top_k=5,
    )


# 直接运行本文件时 __name__ 等于 "__main__"；被导入时不会执行 main()。
if __name__ == "__main__":
    main()
