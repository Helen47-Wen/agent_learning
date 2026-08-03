"""
最小 RAG 示例：使用 Ollama 生成文本向量，使用 DeepSeek 生成最终答案。

整体运行逻辑：

    用户问题 + 示例资料 DOCUMENTS
                 │
                 ▼
        Ollama Embedding API
        分别生成问题向量和资料向量
                 │
                 ▼
          计算余弦相似度
                 │
                 ▼
       按相似度排序并选出 Top-K
                 │
                 ▼
        将 Top-K 资料组装成上下文
                 │
                 ▼
       DeepSeek Chat Completions API
                 │
                 ▼
           输出基于资料的答案

终端指令（在项目根目录执行）：

1. 首次使用时，下载默认的 Embedding 模型：
    ollama pull qwen3-embedding:8b

2. 如果 Ollama 服务尚未启动，启动本地服务（保持这个终端运行）：
    ollama serve
    
    **********
    ssh -N -L 11434:127.0.0.1:11434 ubuntu@10.14.52.65 -p 4004
    *********

3. 可在另一个终端确认 Ollama 服务和模型是否可用：
    curl http://127.0.0.1:11434/api/tags

4. 运行本示例：
    python day08_rag_foundations/examples/01_min_rag_demo.py

运行前请确认：
1. `.env` 中已配置 OPENAI_API_KEY、OPENAI_BASE_URL 和 OPENAI_MODEL；
2. `.env` 可选配置 OLLAMA_BASE_URL 和 OLLAMA_EMBEDDING_MODEL；
3. 如果使用远程 Ollama，请把 OLLAMA_BASE_URL 设置为远程服务地址，无需在本机运行
   `ollama serve`。
"""

from __future__ import annotations

import math
import os

import requests

from dotenv import load_dotenv
from openai import OpenAI


# ============================================================
# 1. 示例资料：先不用读文件，直接写几段小资料
# ============================================================

DOCUMENTS = [
    {
        "id": "doc_repoops_v0",
        "title": "RepoOps Assistant v0",
        "text": """
    RepoOps Assistant v0 是一个用于分析代码仓库的最小工程 Agent。

    它主要解决的问题是：大模型仅凭用户描述无法可靠了解代码仓库中的真实状态，
    容易对文件、代码和项目结构进行猜测。

    RepoOps Assistant v0 通过 LLM Planner、结构化动作、只读工具、
    Agent 状态、Observation 和 Trace 日志，让大模型能够先获取真实仓库信息，
    再进行分析和决策。

    它重点解决以下问题：
    1. 大模型不了解代码仓库的实时内容；
    2. 大模型可能根据不完整信息进行猜测；
    3. 工具调用过程难以追踪和调试；
    4. 自由文本决策难以被程序稳定执行；
    5. Agent 初期直接修改仓库可能带来安全风险。
    """,
    },
    {
        "id": "doc_rag_intro",
        "title": "RAG 基础",
        "text": """
    RAG 的全称是 Retrieval-Augmented Generation，即检索增强生成。

    它主要解决的问题是：大模型的内部知识可能过时、不完整，
    并且模型在缺少事实依据时可能生成错误信息。

    RAG 在生成答案前，先从外部知识库中检索与问题相关的资料，
    再把这些资料作为上下文交给大模型生成答案。

    因此，RAG 主要用于补充外部知识、降低幻觉，
    并让回答具有更明确的事实依据。
    """,
    },
    {
        "id": "doc_auv_fluent",
        "title": "AUV Fluent Agent",
        "text": (
            "AUV Fluent Simulation Agent 可以把 SolidWorks、SpaceClaim、"
            "Fluent Meshing 和 Fluent Solver 串成自动化流程。"
            "后续可以用 RAG 检索 Fluent 日志、网格质量报告和历史错误修复方案。"
        ),
    },
]


# ============================================================
# 2. 初始化 OpenAI 客户端
# ============================================================

def build_client() -> OpenAI:
    """创建仅用于生成最终答案的 OpenAI 兼容客户端。"""
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")

    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in .env")

    # 配置 base_url 后，可以连接 DeepSeek 等 OpenAI Chat Completions 兼容服务。
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)

    return OpenAI(api_key=api_key)


# ============================================================
# 3. Embedding：把文本变成向量
# ============================================================

def get_embedding(text: str) -> list[float]:
    """调用 Ollama Embedding API，把一段文本转换成一个浮点数向量。"""
    load_dotenv()

    # 这两个配置与上面的对话模型相互独立：Ollama 负责向量化，DeepSeek 负责回答。
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:8b")

    print("\n[EMBEDDING REQUEST]")
    print(f"model: {embedding_model}")
    print(f"text length: {len(text)}")
    print("text preview:")
    print(text[:300])

    response = requests.post(
        f"{ollama_base_url.rstrip('/')}/api/embed",
        json={
            "model": embedding_model,
            "input": text,
        },
        timeout=60,
    )

    # 4xx/5xx 响应在这里立即转换为异常，避免继续处理不完整的数据。
    response.raise_for_status()

    data = response.json()
    # /api/embed 返回 embeddings 列表；当前一次只输入一段文本，因此取第一个向量。
    embeddings = data.get("embeddings")

    if not embeddings:
        raise RuntimeError(f"No embeddings returned from Ollama: {data}")

    embedding = embeddings[0]

    print("[EMBEDDING RESPONSE]")
    print(f"embedding dimension: {len(embedding)}")
    print(f"first 5 values: {embedding[:5]}")

    return embedding


# ============================================================
# 4. 相似度计算：比较两个向量有多接近
# ============================================================

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度；结果越大，表示文本语义越接近。"""
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


# ============================================================
# 5. 检索：找出和问题最相关的资料
# ============================================================

def retrieve_relevant_documents(
    question: str,
    top_k: int = 2,
) -> list[dict]:
    """为问题和资料生成向量，并返回相似度最高的 top_k 条资料。"""
    question_embedding = get_embedding(question)

    scored_documents = []

    for document in DOCUMENTS:
        # 教学示例在每次查询时重新生成资料向量；实际项目通常会预先生成并缓存。
        document_embedding = get_embedding(document["text"])

        score = cosine_similarity(
            question_embedding,
            document_embedding,
        )

        scored_documents.append(
            {
                "id": document["id"],
                "title": document["title"],
                "text": document["text"],
                "score": score,
            }
        )

    # 按相似度从高到低排序，然后只保留最相关的 top_k 条资料。
    scored_documents.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return scored_documents[:top_k]


# ============================================================
# 6. 生成回答：把检索结果交给大模型
# ============================================================

def build_context(retrieved_documents: list[dict]) -> str:
    """把检索结果整理成结构清晰、可直接发送给大模型的上下文。"""
    blocks = []

    for index, document in enumerate(retrieved_documents, start=1):
        block = "\n".join(
            [
                f"[资料 {index}]",
                f"id: {document['id']}",
                f"title: {document['title']}",
                f"score: {document['score']:.4f}",
                "content:",
                document["text"],
            ]
        )
        blocks.append(block)

    return "\n\n---\n\n".join(blocks)


def answer_with_rag(
    client: OpenAI,
    question: str,
    retrieved_documents: list[dict],
) -> str:
    """要求大模型严格依据检索到的资料生成答案。"""
    # 对话模型由 OPENAI_MODEL 控制；Embedding 模型由 OLLAMA_EMBEDDING_MODEL 控制。
    model = os.getenv("OPENAI_MODEL", "deepseek-v4-flash")

    context = build_context(retrieved_documents)

    print("\n[CONTEXT SENT TO LLM]")
    print(context)

    # 约束回答只能基于检索资料，减少模型脱离资料自由发挥的情况。
    system_prompt = (
        "你是一个 RAG 学习助手。"
        "请只根据提供的资料回答问题。"
        "如果资料不足，请明确说明资料不足，不要编造。"
    )

    user_prompt = f"""
    用户问题：
    {question}

    检索到的资料：
    {context}

    请基于以上资料，用中文回答。
    """

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    )

    return completion.choices[0].message.content or ""

# ============================================================
# 7. 主程序
# ============================================================

def main() -> None:
    """串联客户端初始化、资料检索和答案生成，完成最小 RAG 流程。"""
    client = build_client()

    # 为了让示例可直接运行，这里先使用一个固定问题。
    question = "RepoOps Assistant v0 和 RAG 分别解决什么问题？"

    print("\n[QUESTION]")
    print(question)

    retrieved_documents = retrieve_relevant_documents(
        question=question,
        top_k=2,
    )

    print("\n[RETRIEVED DOCUMENTS]")
    for document in retrieved_documents:
        print(
            f"- {document['title']} "
            f"(id={document['id']}, score={document['score']:.4f})"
        )

    answer = answer_with_rag(
        client=client,
        question=question,
        retrieved_documents=retrieved_documents,
    )

    print("\n[ANSWER]")
    print(answer)


if __name__ == "__main__":
    main()
