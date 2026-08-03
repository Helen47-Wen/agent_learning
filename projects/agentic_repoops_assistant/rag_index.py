"""项目代码库的轻量级 RAG 索引与检索模块。

核心流程：扫描文件 → 文本切块 → Ollama 向量化 → JSONL 持久化
→ 问题向量化 → 余弦相似度排序 → 返回 top_k 文本块。

直接运行本文件会重建索引；导入本模块后可调用 ``retrieve_chunks`` 完成检索。
语法与实现重点已标注在对应代码附近。
"""

# 延迟解析类型注解；类型注解用于静态提示，不会自动校验运行时数据。
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


# __file__ 是当前文件路径；resolve() 转为绝对路径，parent 取得所在目录。
PROJECT_DIR = Path(__file__).resolve().parent
# 索引保存在独立目录中；该目录会在文件扫描阶段被排除，避免重复索引自身。
RAG_STORE_DIR = PROJECT_DIR / "rag_store"
INDEX_PATH = RAG_STORE_DIR / "repoops_rag_index.jsonl"


def should_index_file(path: Path) -> bool:
    """
    判断文件是否应该进入 RAG 索引。

    只接收常见的纯文本格式，并排除依赖、缓存、密钥文件和索引输出目录。
    """
    ignored_parts = {
        ".git",
        "__pycache__",
        "logs",
        "rag_store",
        ".venv",
        "venv",
        "node_modules",
    }

    # path.parts 把路径拆成各级名称；生成器逐项检查，any() 遇到 True 就提前停止。
    if any(part in ignored_parts for part in path.parts):
        return False

    if path.name in {".env", ".DS_Store"}:
        return False

    allowed_suffixes = {
        ".md",
        ".py",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
    }

    # suffix 取得扩展名；lower() 让 .PY 和 .py 按相同规则判断。
    return path.suffix.lower() in allowed_suffixes


def iter_project_files(project_dir: Path) -> list[Path]:
    """
    递归收集项目内所有可索引的文本文件。

    ``list[Path]`` 表示返回值是由 Path 对象组成的列表；类型注解不改变运行行为。
    """
    files: list[Path] = []

    # rglob("*") 递归遍历 project_dir 下的所有层级。
    for path in project_dir.rglob("*"):
        if path.is_file() and should_index_file(path):
            files.append(path)

    return files


def chunk_text(
    text: str,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> list[dict[str, Any]]:
    """
    把长文本切成多个 chunk。

    ``overlap`` 让相邻文本块保留一段重复上下文，降低语义刚好在边界处
    被截断的概率。返回的字符位置基于原始文本，可用于定位内容来源。
    正常使用需要满足 ``0 <= overlap < chunk_size``，保证 start 持续向前推进。

    返回类型 ``list[dict[str, Any]]`` 表示“字典列表”；Any 表示字典值可以是
    整数、字符串等不同类型。
    """
    chunks: list[dict[str, Any]] = []

    # 空文本无需进入 while；提前 return 也让后续逻辑少一层缩进。
    if not text.strip():
        return chunks

    start = 0
    text_length = len(text)

    while start < text_length:
        # min() 防止最后一个 chunk 的 end 超过文本长度。
        end = min(start + chunk_size, text_length)
        # [start:end] 是左闭右开切片：包含 start，不包含 end。
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(
                {
                    "start_char": start,
                    "end_char": end,
                    "text": chunk,
                }
            )

        # 已到文本末尾时主动结束 while，避免继续生成重复块。
        if end == text_length:
            break

        # 下一块从当前块末尾向前回退 overlap 个字符，形成上下文重叠。
        start = max(0, end - overlap)

    return chunks


def get_embedding(text: str) -> list[float]:
    """
    调用 Ollama Embed API 为文本生成向量。

    服务地址和模型均可通过环境变量覆盖，默认使用本机 Ollama 与
    ``qwen3-embedding:8b``。
    """
    load_dotenv()

    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:8b")

    # POST 请求体中的 input 是待向量化文本；返回值是浮点数组 list[float]。
    response = requests.post(
        f"{ollama_base_url.rstrip('/')}/api/embed",
        json={
            "model": embedding_model,
            "input": text,
        },
        timeout=120,
    )

    # 4xx/5xx 响应会在这里抛出异常，避免把错误响应继续当作 embedding 解析。
    response.raise_for_status()

    data = response.json()
    embeddings = data.get("embeddings")

    if not embeddings:
        raise RuntimeError(f"No embeddings returned from Ollama: {data}")

    return embeddings[0]


def build_rag_index(
    project_dir: Path = PROJECT_DIR,
    index_path: Path = INDEX_PATH,
) -> None:
    """
    为项目文件构建 RAG 索引，并将全部记录写入 JSONL 文件。

    每条记录对应一个文本块，包含稳定的块 ID、源文件路径、原文字符范围、
    文本内容及 embedding。核心数据流是“读取 → 切块 → 向量化 → 写入”，
    每次调用都会完整重建索引文件。
    """
    files = iter_project_files(project_dir)

    print(f"[INFO] Project dir: {project_dir}")
    print(f"[INFO] Files to index: {len(files)}")

    records: list[dict[str, Any]] = []

    for file_path in files:
        # relative_to() 去掉项目根目录，as_posix() 统一使用 / 作为分隔符。
        relative_path = file_path.relative_to(project_dir).as_posix()
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_text(text)

        print(f"[INDEX] {relative_path} | chunks={len(chunks)}")

        # enumerate() 同时提供序号和 chunk，用序号构造稳定、可定位的 ID。
        for chunk_index, chunk in enumerate(chunks):
            chunk_id = f"{relative_path}::chunk_{chunk_index}"
            # embedding 调用通常是构建阶段最耗时的步骤，每个 chunk 调用一次。
            embedding = get_embedding(chunk["text"])

            records.append(
                {
                    "chunk_id": chunk_id,
                    "source_path": relative_path,
                    "start_char": chunk["start_char"],
                    "end_char": chunk["end_char"],
                    "text": chunk["text"],
                    "embedding": embedding,
                }
            )

    # parents=True 递归创建父目录；exist_ok=True 表示目录已存在时不报错。
    index_path.parent.mkdir(parents=True, exist_ok=True)

    # 使用 JSONL 方便逐条读取，也避免把整个索引包装成一个大型 JSON 数组。
    # with 是上下文管理器：正常结束或发生异常时都会自动关闭文件。
    with index_path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"[DONE] Indexed chunks: {len(records)}")
    print(f"[DONE] Index saved to: {index_path}")


def load_rag_index(index_path: Path = INDEX_PATH) -> list[dict[str, Any]]:
    """
    逐行读取本地 JSONL 索引并还原为记录列表。
    """
    if not index_path.exists():
        raise FileNotFoundError(f"RAG index not found: {index_path}")

    records: list[dict[str, Any]] = []

    # 与写入端对应：逐行读取 JSONL，每一行单独 json.loads()。
    with index_path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                records.append(json.loads(line))

    return records


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    计算两个 embedding 向量的余弦相似度，值越大表示语义越接近。

    公式为“点积 /（向量 a 的模 × 向量 b 的模）”。
    """
    # zip(a, b) 按相同位置配对；生成器逐项相乘后由 sum() 求出点积。
    dot_product = sum(x * y for x, y in zip(a, b))
    # 各维平方和再开方，得到两个向量的长度（L2 范数）。
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    # 零向量没有可计算的方向，提前返回以避免除零。
    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def retrieve_chunks(
    question: str,
    top_k: int = 5,
    index_path: Path = INDEX_PATH,
) -> list[dict[str, Any]]:
    """
    根据用户问题检索余弦相似度最高的 ``top_k`` 个文本块。

    这是全量扫描检索：问题只向量化一次，再与索引中的每条向量逐一比较。
    查询和建索引必须使用同一个 embedding 模型，否则向量不可比较。
    """
    records = load_rag_index(index_path)
    question_embedding = get_embedding(question)

    scored_chunks: list[dict[str, Any]] = []

    for record in records:
        score = cosine_similarity(question_embedding, record["embedding"])

        scored_chunks.append(
            {
                "chunk_id": record["chunk_id"],
                "source_path": record["source_path"],
                "score": score,
                "text": record["text"],
                "start_char": record["start_char"],
                "end_char": record["end_char"],
            }
        )

    # key 接收一个函数；lambda 指定用每条记录的 score 作为排序依据。
    # reverse=True 表示降序，最相关的文本块排在列表前部。
    scored_chunks.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return scored_chunks[:top_k]


def main() -> None:
    build_rag_index()


# 直接运行本文件时 __name__ 等于 "__main__"；被导入时不会执行 main()。
if __name__ == "__main__":
    main()
