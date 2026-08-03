"""RepoOps Assistant 的检索效果评估脚本。

核心流程：读取 JSONL 测试集 → 调用检索器 → 统一结果格式
→ 计算 Hit@K、首个相关排名、MRR、关键词召回率和延迟 → 输出并保存报告。

本文件只评估“检索是否找到正确资料”，不调用聊天模型评估最终答案质量。
语法、兼容性处理与指标公式已标注在对应代码附近。
"""

# 延迟解析类型注解；类型注解用于静态提示，不会自动校验运行时数据。
from __future__ import annotations

import inspect
import json
import time
from pathlib import Path
from typing import Any

# 复用正式问答流程中的检索函数，保证离线评估与实际应用使用同一套逻辑。
from rag_index import retrieve_chunks


# __file__ 是当前文件路径；resolve() 转为绝对路径，parent 取得所在目录。
PROJECT_DIR = Path(__file__).resolve().parent

# 圆括号允许把较长的路径拼接拆成多行；Path 的 / 运算符负责拼接各级路径。
DEFAULT_CASES_PATH = (
    PROJECT_DIR
    / "evals"
    / "retrieval_eval_cases.jsonl"
)

DEFAULT_INDEX_PATH = (
    PROJECT_DIR
    / "rag_store"
    / "repoops_rag_index.jsonl"
)

DEFAULT_RESULT_PATH = (
    PROJECT_DIR
    / "evals"
    / "retrieval_eval_results.json"
)


def load_eval_cases(cases_path: Path) -> list[dict[str, Any]]:
    """
    从 JSONL 文件中读取测试题。

    JSONL 每行是一个独立 JSON 对象，一行解析失败时可以准确报告行号。
    返回类型 ``list[dict[str, Any]]`` 表示由测试题字典组成的列表。
    """
    cases: list[dict[str, Any]] = []

    # with 是上下文管理器：读取结束或发生异常时都会自动关闭文件。
    with cases_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        # enumerate(..., start=1) 同时取得行号和内容，并让行号与编辑器一致。
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            # continue 跳过空行，直接进入下一轮循环。
            if not line:
                continue

            # 只把 JSON 格式错误转换为更清晰的业务错误，其他异常继续向外抛出。
            try:
                case = json.loads(line)
            except json.JSONDecodeError as error:
                # raise ... from error 保留原始异常，便于查看完整错误链。
                raise ValueError(
                    f"第 {line_number} 行不是合法 JSON：{error}"
                ) from error

            cases.append(case)

    return cases


def call_retriever(
    question: str,
    top_k: int,
) -> list[Any]:
    """
    调用已有的 retrieve_chunks()。

    这里使用反射检查函数参数，兼容 ``question/query`` 和
    ``index_path/index_file`` 等不同版本的命名。
    """
    # inspect.signature() 在运行时读取函数签名，parameters 是参数名映射。
    signature = inspect.signature(retrieve_chunks)
    parameters = signature.parameters

    # kwargs 收集可选的关键字参数，稍后通过 ** 解包传给检索函数。
    kwargs: dict[str, Any] = {}

    if "top_k" in parameters:
        kwargs["top_k"] = top_k

    if "index_path" in parameters:
        kwargs["index_path"] = DEFAULT_INDEX_PATH
    elif "index_file" in parameters:
        kwargs["index_file"] = DEFAULT_INDEX_PATH

    if "question" in parameters:
        kwargs["question"] = question
        results = retrieve_chunks(**kwargs)
    elif "query" in parameters:
        kwargs["query"] = question
        results = retrieve_chunks(**kwargs)
    else:
        # 如果无法识别问题参数名，就把 question 作为第一个位置参数传入。
        results = retrieve_chunks(question, **kwargs)

    # list() 将任意可迭代结果统一转换为列表，方便后续重复遍历。
    return list(results)


def chunk_to_dict(chunk: Any) -> dict[str, Any]:
    """
    把检索结果统一转换成字典。

    兼容：
    1. 普通 dict
    2. Pydantic 对象
    3. 普通 Python 对象
    """
    # isinstance() 先处理当前 retrieve_chunks 返回的普通字典。
    if isinstance(chunk, dict):
        return chunk

    # hasattr() 用于能力检测，而不是把代码绑定到某个具体对象类型。
    if hasattr(chunk, "model_dump"):
        return chunk.model_dump()

    if hasattr(chunk, "__dict__"):
        # vars(obj) 读取普通 Python 对象的 __dict__ 属性。
        return vars(chunk)

    raise TypeError(
        f"无法识别检索结果类型：{type(chunk)}"
    )


def get_chunk_source(chunk: dict[str, Any]) -> str:
    """
    从检索结果中提取文件来源。
    """
    # 按优先级尝试多个字段名，兼容不同版本的检索结果结构。
    possible_keys = [
        "source_path",
        "source",
        "file_path",
        "path",
    ]

    for key in possible_keys:
        # dict.get() 在键不存在时返回 None，不会像 chunk[key] 一样抛 KeyError。
        value = chunk.get(key)

        if value:
            return str(value)

    return ""


def get_chunk_text(chunk: dict[str, Any]) -> str:
    """
    从检索结果中提取文本内容。
    """
    # 与来源字段相同：依次尝试可能的文本字段名。
    possible_keys = [
        "text",
        "content",
        "chunk_text",
    ]

    for key in possible_keys:
        value = chunk.get(key)

        if value:
            return str(value)

    return ""


def get_chunk_score(chunk: dict[str, Any]) -> float:
    """
    从检索结果中提取相似度分数。
    """
    # 第二个参数 0.0 是 score 缺失时的默认值。
    value = chunk.get("score", 0.0)

    try:
        return float(value)
    # 一个 except 元组可以同时捕获类型错误和无法转换的字符串。
    except (TypeError, ValueError):
        return 0.0


def find_first_relevant_rank(
    retrieved_chunks: list[dict[str, Any]],
    expected_source_contains: list[str],
) -> int | None:
    """
    查找第一个正确来源的排名，用于计算 Hit@K 和 Reciprocal Rank。

    返回值示例：
    1：正确资料排第 1
    2：正确资料排第 2
    None：top_k 中没有正确资料
    """
    if not expected_source_contains:
        return None

    # 列表推导式统一转为小写，使来源匹配不区分大小写。
    expected_values = [
        value.lower()
        for value in expected_source_contains
    ]

    for rank, chunk in enumerate(
        retrieved_chunks,
        start=1,
    ):
        source = get_chunk_source(chunk).lower()

        # 生成器逐项检查；any() 命中任一预期片段就提前停止。
        if any(
            expected in source
            for expected in expected_values
        ):
            return rank

    return None


def calculate_keyword_recall(
    retrieved_chunks: list[dict[str, Any]],
    expected_keywords: list[str],
) -> tuple[float, list[str], list[str]]:
    """
    计算检索文本覆盖了多少预期关键词。

    公式：Keyword Recall = 命中关键词数 / 预期关键词总数。
    元组返回值依次为召回率、已命中关键词和缺失关键词。
    """
    if not expected_keywords:
        return 1.0, [], []

    # 生成器提取各 chunk 文本，join() 将它们合并为统一检索上下文。
    context = "\n".join(
        get_chunk_text(chunk)
        for chunk in retrieved_chunks
    ).lower()

    matched_keywords: list[str] = []
    missing_keywords: list[str] = []

    for keyword in expected_keywords:
        if keyword.lower() in context:
            matched_keywords.append(keyword)
        else:
            missing_keywords.append(keyword)

    # 使用浮点除法得到 0～1 的召回率。
    recall = (
        len(matched_keywords)
        / len(expected_keywords)
    )

    return recall, matched_keywords, missing_keywords


def evaluate_one_case(
    case: dict[str, Any],
    top_k: int,
) -> dict[str, Any]:
    """
    评估一道测试题，返回指标和精简后的检索结果。
    """
    # question 是必填字段，使用 [] 让缺失字段立即抛出 KeyError。
    question = str(case["question"])

    # 预期关键词和来源是可选字段，缺失时用空列表。
    expected_keywords = case.get(
        "expected_keywords",
        [],
    )

    expected_source_contains = case.get(
        "expected_source_contains",
        [],
    )

    # perf_counter() 是适合测量短时间间隔的高精度单调时钟。
    start_time = time.perf_counter()

    raw_chunks = call_retriever(
        question=question,
        top_k=top_k,
    )

    latency_seconds = (
        time.perf_counter()
        - start_time
    )

    # 列表推导式把不同类型的原始结果统一转换为字典。
    retrieved_chunks = [
        chunk_to_dict(chunk)
        for chunk in raw_chunks
    ]

    first_relevant_rank = find_first_relevant_rank(
        retrieved_chunks,
        expected_source_contains,
    )

    # Hit@K：top_k 结果中是否至少出现一个预期来源。
    if expected_source_contains:
        source_hit = first_relevant_rank is not None
        # Reciprocal Rank = 1 / 首个相关结果排名；未命中时为 0。
        reciprocal_rank = (
            1.0 / first_relevant_rank
            if first_relevant_rank
            else 0.0
        )
    else:
        source_hit = None
        reciprocal_rank = None

    # 元组解包：一次接收 calculate_keyword_recall() 返回的三个值。
    (
        keyword_recall,
        matched_keywords,
        missing_keywords,
    ) = calculate_keyword_recall(
        retrieved_chunks,
        expected_keywords,
    )

    simplified_chunks: list[dict[str, Any]] = []

    for rank, chunk in enumerate(
        retrieved_chunks,
        start=1,
    ):
        simplified_chunks.append(
            {
                "rank": rank,
                "source": get_chunk_source(chunk),
                "score": get_chunk_score(chunk),
                # [:160] 是左闭右开切片，只保留前 160 个字符用于报告预览。
                "text_preview": get_chunk_text(chunk)[:160],
            }
        )

    return {
        "case_id": case.get("case_id", ""),
        "question": question,
        "top_k": top_k,
        "source_hit": source_hit,
        "first_relevant_rank": first_relevant_rank,
        "reciprocal_rank": reciprocal_rank,
        "keyword_recall": keyword_recall,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "latency_seconds": latency_seconds,
        "retrieved_chunks": simplified_chunks,
    }


def print_case_result(result: dict[str, Any]) -> None:
    """
    在终端中打印单道题的结果。
    """
    # 字符串乘法快速生成固定长度的终端分隔线。
    print("\n" + "=" * 70)
    print(f"[CASE] {result['case_id']}")
    print(f"[QUESTION] {result['question']}")

    if result["source_hit"] is not None:
        print(
            f"[SOURCE HIT@{result['top_k']}] "
            f"{result['source_hit']}"
        )

        print(
            "[FIRST RELEVANT RANK] "
            f"{result['first_relevant_rank']}"
        )

        print(
            "[RECIPROCAL RANK] "
            f"{result['reciprocal_rank']:.4f}"
        )

    print(
        "[KEYWORD RECALL] "
        # :.2% 把 0～1 的小数显示为保留两位的百分比。
        f"{result['keyword_recall']:.2%}"
    )

    print(
        "[MATCHED KEYWORDS] "
        f"{result['matched_keywords']}"
    )

    print(
        "[MISSING KEYWORDS] "
        f"{result['missing_keywords']}"
    )

    print(
        "[LATENCY] "
        f"{result['latency_seconds']:.3f}s"
    )

    print("\n[RETRIEVED CHUNKS]")

    for chunk in result["retrieved_chunks"]:
        print(
            f"- rank={chunk['rank']} "
            f"score={chunk['score']:.4f} "
            f"source={chunk['source']}"
        )
        print(
            f"  preview={chunk['text_preview']}"
        )


def build_summary(
    results: list[dict[str, Any]],
    top_k: int,
) -> dict[str, Any]:
    """
    汇总所有测试题的评估指标。

    Hit@K 是命中来源的题目占比；MRR 是所有题 Reciprocal Rank 的平均值。
    """
    # 只用配置了预期来源的题目计算 Hit@K 和 MRR。
    source_results = [
        result
        for result in results
        if result["source_hit"] is not None
    ]

    if source_results:
        # 布尔命中转为 1，未命中不进入 sum，最后除以题目数。
        hit_rate = sum(
            1
            for result in source_results
            if result["source_hit"]
        ) / len(source_results)

        # MRR（Mean Reciprocal Rank）= 各题 Reciprocal Rank 的平均值。
        mrr = sum(
            result["reciprocal_rank"]
            for result in source_results
        ) / len(source_results)
    else:
        hit_rate = None
        mrr = None

    average_keyword_recall = sum(
        result["keyword_recall"]
        for result in results
    ) / len(results)

    average_latency = sum(
        result["latency_seconds"]
        for result in results
    ) / len(results)

    return {
        "total_cases": len(results),
        "top_k": top_k,
        # f-string 让结果键随 top_k 动态变为 hit_at_3、hit_at_5 等。
        f"hit_at_{top_k}": hit_rate,
        "mrr": mrr,
        "average_keyword_recall": average_keyword_recall,
        "average_latency_seconds": average_latency,
    }


def print_summary(summary: dict[str, Any]) -> None:
    """
    打印汇总指标。
    """
    print("\n" + "#" * 70)
    print("[EVALUATION SUMMARY]")
    print(f"total cases: {summary['total_cases']}")
    print(f"top_k: {summary['top_k']}")

    # 使用与 build_summary() 相同的规则构造动态指标键。
    hit_key = f"hit_at_{summary['top_k']}"
    hit_rate = summary[hit_key]

    if hit_rate is not None:
        print(
            f"Hit@{summary['top_k']}: "
            f"{hit_rate:.2%}"
        )

    if summary["mrr"] is not None:
        print(
            f"MRR: {summary['mrr']:.4f}"
        )

    print(
        "Average Keyword Recall: "
        f"{summary['average_keyword_recall']:.2%}"
    )

    print(
        "Average Retrieval Latency: "
        f"{summary['average_latency_seconds']:.3f}s"
    )


def save_results(
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    result_path: Path,
) -> None:
    """
    把汇总指标和每道题的详细结果保存为格式化 JSON。
    """
    result_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "summary": summary,
        "results": results,
    }

    # "w" 是覆盖写入模式；with 会在写入结束或异常时自动关闭文件。
    with result_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        # ensure_ascii=False 保留中文，indent=2 让结果便于人工阅读。
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )


def main() -> None:
    """编排完整评估流程：加载、逐题评估、汇总、打印并保存。"""
    top_k = 3

    cases = load_eval_cases(
        DEFAULT_CASES_PATH
    )

    if not cases:
        raise ValueError(
            "评估数据集为空，请先添加测试题。"
        )

    results: list[dict[str, Any]] = []

    # 逐题调用真实检索器，因此总耗时包含每道题的问题向量生成时间。
    for case in cases:
        result = evaluate_one_case(
            case=case,
            top_k=top_k,
        )

        results.append(result)
        print_case_result(result)

    summary = build_summary(
        results=results,
        top_k=top_k,
    )

    print_summary(summary)

    save_results(
        results=results,
        summary=summary,
        result_path=DEFAULT_RESULT_PATH,
    )

    print(
        "\n[DONE] Evaluation results saved to:"
    )
    print(DEFAULT_RESULT_PATH)


# 直接运行本文件时 __name__ 等于 "__main__"；被导入时不会执行 main()。
if __name__ == "__main__":
    main()
