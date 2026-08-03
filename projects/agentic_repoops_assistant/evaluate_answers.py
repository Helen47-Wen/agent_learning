from __future__ import annotations

import inspect
import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

from rag_index import retrieve_chunks


PROJECT_DIR = Path(__file__).resolve().parent
ROOT_DIR = PROJECT_DIR.parents[1]

CASES_PATH = (
    PROJECT_DIR
    / "evals"
    / "answer_eval_cases.jsonl"
)

INDEX_PATH = (
    PROJECT_DIR
    / "rag_store"
    / "repoops_rag_index.jsonl"
)

RESULT_PATH = (
    PROJECT_DIR
    / "evals"
    / "answer_eval_results.json"
)

TOP_K = 3
PASS_SCORE = 4


# 先尝试读取 agent_learning/.env
load_dotenv(ROOT_DIR / ".env")

# 如果项目目录里也有 .env，则补充读取
# override=False 表示不覆盖已经读取到的环境变量
load_dotenv(
    PROJECT_DIR / ".env",
    override=False,
)


class JudgeResult(BaseModel):
    """
    评估模型必须返回的结构化结果。
    """

    correctness_score: int = Field(
        ge=1,
        le=5,
        description="回答正确性分数",
    )
    correctness_reason: str

    relevance_score: int = Field(
        ge=1,
        le=5,
        description="回答相关性分数",
    )
    relevance_reason: str

    faithfulness_score: int = Field(
        ge=1,
        le=5,
        description="回答忠实度分数",
    )
    faithfulness_reason: str

    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="无法从检索上下文得到支持的声明",
    )


def create_client() -> OpenAI:
    """
    根据 .env 创建聊天模型客户端。
    """
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")

    if not api_key:
        raise ValueError(
            "没有找到 OPENAI_API_KEY，"
            "请检查项目根目录中的 .env。"
        )

    client_kwargs: dict[str, Any] = {
        "api_key": api_key,
    }

    if base_url:
        client_kwargs["base_url"] = base_url

    return OpenAI(**client_kwargs)


def get_model_names() -> tuple[str, str]:
    """
    返回：
    1. 生成回答所使用的模型
    2. 评估回答所使用的模型

    如果没有设置 OPENAI_JUDGE_MODEL，
    暂时让评估模型与回答模型相同。
    """
    answer_model = os.getenv("OPENAI_MODEL")

    if not answer_model:
        raise ValueError(
            "没有找到 OPENAI_MODEL，"
            "请检查 .env。"
        )

    judge_model = os.getenv(
        "OPENAI_JUDGE_MODEL",
        answer_model,
    )

    return answer_model, judge_model


def call_chat_model(
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],
    json_mode: bool = False,
) -> str:
    """
    调用聊天模型。

    json_mode=True 时优先请求 JSON 输出。
    如果当前 API 不支持 response_format，
    则自动退回普通文本调用。
    """
    request_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }

    if json_mode:
        try:
            response = client.chat.completions.create(
                **request_kwargs,
                response_format={
                    "type": "json_object",
                },
            )
        except Exception as error:
            error_message = str(error).lower()

            unsupported_json_mode = any(
                keyword in error_message
                for keyword in [
                    "response_format",
                    "json_object",
                    "json mode",
                    "unsupported parameter",
                ]
            )

            if not unsupported_json_mode:
                raise

            print(
                "[WARN] 当前 API 不支持 JSON mode，"
                "已退回普通文本输出。"
            )

            response = client.chat.completions.create(
                **request_kwargs
            )
    else:
        response = client.chat.completions.create(
            **request_kwargs
        )

    content = response.choices[0].message.content

    if not content:
        raise RuntimeError(
            "聊天模型返回了空内容。"
        )

    return content.strip()


def load_eval_cases(
    cases_path: Path,
) -> list[dict[str, Any]]:
    """
    从 JSONL 文件读取回答评估测试集。
    """
    cases: list[dict[str, Any]] = []

    with cases_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line_number, line in enumerate(
            file,
            start=1,
        ):
            line = line.strip()

            if not line:
                continue

            try:
                case = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"测试集第 {line_number} 行"
                    f"不是合法 JSON：{error}"
                ) from error

            required_fields = {
                "case_id",
                "question",
                "reference_answer",
            }

            missing_fields = (
                required_fields - case.keys()
            )

            if missing_fields:
                raise ValueError(
                    f"测试集第 {line_number} 行"
                    f"缺少字段：{missing_fields}"
                )

            cases.append(case)

    return cases


def call_retriever(
    question: str,
    top_k: int,
) -> list[Any]:
    """
    调用现有的 retrieve_chunks()。

    inspect.signature() 用于查看函数参数，
    从而兼容 question/query 等不同命名。
    """
    signature = inspect.signature(
        retrieve_chunks
    )

    parameters = signature.parameters
    kwargs: dict[str, Any] = {}

    if "top_k" in parameters:
        kwargs["top_k"] = top_k

    if "index_path" in parameters:
        kwargs["index_path"] = INDEX_PATH
    elif "index_file" in parameters:
        kwargs["index_file"] = INDEX_PATH

    if "question" in parameters:
        kwargs["question"] = question
        raw_results = retrieve_chunks(**kwargs)

    elif "query" in parameters:
        kwargs["query"] = question
        raw_results = retrieve_chunks(**kwargs)

    else:
        raw_results = retrieve_chunks(
            question,
            **kwargs,
        )

    return list(raw_results)


def chunk_to_dict(
    chunk: Any,
) -> dict[str, Any]:
    """
    将检索结果统一转换为字典。
    """
    if isinstance(chunk, dict):
        return chunk

    if hasattr(chunk, "model_dump"):
        return chunk.model_dump()

    if hasattr(chunk, "__dict__"):
        return vars(chunk)

    raise TypeError(
        f"无法识别检索结果类型：{type(chunk)}"
    )


def get_chunk_text(
    chunk: dict[str, Any],
) -> str:
    """
    从不同格式的 chunk 中提取正文。
    """
    for key in [
        "text",
        "content",
        "chunk_text",
    ]:
        value = chunk.get(key)

        if value:
            return str(value)

    return ""


def get_chunk_source(
    chunk: dict[str, Any],
) -> str:
    """
    从不同格式的 chunk 中提取来源路径。
    """
    for key in [
        "source_path",
        "source",
        "file_path",
        "path",
    ]:
        value = chunk.get(key)

        if value:
            return str(value)

    return "unknown"


def get_chunk_score(
    chunk: dict[str, Any],
) -> float:
    """
    提取相似度分数。
    """
    value = chunk.get("score", 0.0)

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def format_context(
    chunks: list[dict[str, Any]],
) -> str:
    """
    将 top_k chunks 整理成发送给聊天模型的 context。
    """
    context_blocks: list[str] = []

    for rank, chunk in enumerate(
        chunks,
        start=1,
    ):
        source = get_chunk_source(chunk)
        text = get_chunk_text(chunk)

        context_blocks.append(
            f"[资料 {rank}]\n"
            f"来源：{source}\n"
            f"内容：\n{text}"
        )

    return "\n\n".join(context_blocks)


def generate_rag_answer(
    client: OpenAI,
    model: str,
    question: str,
    context: str,
) -> str:
    """
    根据检索上下文生成 RAG 回答。
    """
    system_prompt = """
你是 RepoOps Assistant 的 RAG 问答模块。

请严格遵守以下规则：

1. 只能根据提供的项目资料回答。
2. 不得使用没有出现在资料中的外部知识补充事实。
3. 如果资料不足，请明确说“根据当前检索资料无法确定”。
4. 回答应直接解决问题，不要加入无关背景。
5. 涉及重要事实时，尽量说明资料来源。
""".strip()

    user_prompt = f"""
用户问题：

{question}

检索到的项目资料：

{context}

请基于以上资料回答用户问题。
""".strip()

    return call_chat_model(
        client=client,
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


def extract_json_object(
    raw_text: str,
) -> dict[str, Any]:
    """
    从模型输出中提取 JSON 对象。

    即使模型返回：
    ```json
    {...}
    ```
    也能尝试取出中间的 JSON。
    """
    text = raw_text.strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    start_index = text.find("{")
    end_index = text.rfind("}")

    if start_index == -1 or end_index == -1:
        raise ValueError(
            "评估模型没有返回 JSON 对象：\n"
            f"{raw_text}"
        )

    json_text = text[
        start_index:end_index + 1
    ]

    return json.loads(json_text)


def judge_answer(
    client: OpenAI,
    model: str,
    question: str,
    reference_answer: str,
    retrieved_context: str,
    generated_answer: str,
) -> JudgeResult:
    """
    使用 LLM-as-a-Judge 评估回答。
    """
    system_prompt = """
你是一名严格的 RAG 回答质量评估员。

你需要分别评估三个互相独立的维度。

一、Correctness：正确性
将“生成答案”与“参考答案”比较。
判断生成答案是否包含参考答案中的核心事实，
是否存在事实错误、遗漏或矛盾。

二、Relevance：相关性
只比较“用户问题”和“生成答案”。
判断回答是否直接解决问题，
是否存在无关信息、答非所问或明显冗余。

三、Faithfulness：忠实度
只比较“生成答案”和“检索上下文”。
检查生成答案中的每项事实，
能否从检索上下文直接获得或合理推出。

重要规则：
1. 参考答案不能作为 Faithfulness 的证据。
2. 即使一个事实在现实中是正确的，只要检索上下文没有支持，
   也应列为 unsupported claim。
3. 不要因为文字表达不同就降低 Correctness，
   应比较事实和语义。
4. 三个维度分别打 1 到 5 分。

评分标准：
5：完全满足要求，没有明显问题
4：整体良好，只有轻微遗漏或冗余
3：部分正确，但存在明显遗漏或问题
2：大部分不满足要求
1：严重错误、答非所问或大量无依据内容

必须只返回一个合法 JSON 对象，不要返回 Markdown。
""".strip()

    user_prompt = f"""
用户问题：
{question}

参考答案：
{reference_answer}

检索上下文：
{retrieved_context}

生成答案：
{generated_answer}

请返回以下字段：

{{
  "correctness_score": 1到5的整数,
  "correctness_reason": "评分原因",
  "relevance_score": 1到5的整数,
  "relevance_reason": "评分原因",
  "faithfulness_score": 1到5的整数,
  "faithfulness_reason": "评分原因",
  "unsupported_claims": ["无法从检索上下文支持的声明"]
}}
""".strip()

    raw_result = call_chat_model(
        client=client,
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
        json_mode=True,
    )

    result_data = extract_json_object(
        raw_result
    )

    return JudgeResult.model_validate(
        result_data
    )


def evaluate_one_case(
    client: OpenAI,
    answer_model: str,
    judge_model: str,
    case: dict[str, Any],
    top_k: int,
) -> dict[str, Any]:
    """
    完成一道测试题的完整 RAG 评估。
    """
    case_id = str(case["case_id"])
    question = str(case["question"])
    reference_answer = str(
        case["reference_answer"]
    )

    retrieval_start = time.perf_counter()

    raw_chunks = call_retriever(
        question=question,
        top_k=top_k,
    )

    retrieval_seconds = (
        time.perf_counter()
        - retrieval_start
    )

    chunks = [
        chunk_to_dict(chunk)
        for chunk in raw_chunks
    ]

    context = format_context(chunks)

    generation_start = time.perf_counter()

    generated_answer = generate_rag_answer(
        client=client,
        model=answer_model,
        question=question,
        context=context,
    )

    generation_seconds = (
        time.perf_counter()
        - generation_start
    )

    judge_start = time.perf_counter()

    judge_result = judge_answer(
        client=client,
        model=judge_model,
        question=question,
        reference_answer=reference_answer,
        retrieved_context=context,
        generated_answer=generated_answer,
    )

    judge_seconds = (
        time.perf_counter()
        - judge_start
    )

    passed = all(
        score >= PASS_SCORE
        for score in [
            judge_result.correctness_score,
            judge_result.relevance_score,
            judge_result.faithfulness_score,
        ]
    )

    retrieved_chunks = []

    for rank, chunk in enumerate(
        chunks,
        start=1,
    ):
        retrieved_chunks.append(
            {
                "rank": rank,
                "source": get_chunk_source(chunk),
                "score": get_chunk_score(chunk),
                "text_preview": (
                    get_chunk_text(chunk)[:200]
                ),
            }
        )

    return {
        "case_id": case_id,
        "question": question,
        "reference_answer": reference_answer,
        "generated_answer": generated_answer,
        "correctness_score": (
            judge_result.correctness_score
        ),
        "correctness_reason": (
            judge_result.correctness_reason
        ),
        "relevance_score": (
            judge_result.relevance_score
        ),
        "relevance_reason": (
            judge_result.relevance_reason
        ),
        "faithfulness_score": (
            judge_result.faithfulness_score
        ),
        "faithfulness_reason": (
            judge_result.faithfulness_reason
        ),
        "unsupported_claims": (
            judge_result.unsupported_claims
        ),
        "passed": passed,
        "retrieval_seconds": retrieval_seconds,
        "generation_seconds": generation_seconds,
        "judge_seconds": judge_seconds,
        "retrieved_chunks": retrieved_chunks,
    }


def print_case_result(
    result: dict[str, Any],
) -> None:
    """
    在终端展示单道题的评估结果。
    """
    print("\n" + "=" * 72)
    print(f"[CASE] {result['case_id']}")
    print(f"[QUESTION] {result['question']}")

    print("\n[GENERATED ANSWER]")
    print(result["generated_answer"])

    print("\n[SCORES]")
    print(
        "Correctness: "
        f"{result['correctness_score']}/5"
    )
    print(
        "Relevance: "
        f"{result['relevance_score']}/5"
    )
    print(
        "Faithfulness: "
        f"{result['faithfulness_score']}/5"
    )
    print(f"Passed: {result['passed']}")

    print("\n[JUDGE REASONS]")
    print(
        "Correctness: "
        f"{result['correctness_reason']}"
    )
    print(
        "Relevance: "
        f"{result['relevance_reason']}"
    )
    print(
        "Faithfulness: "
        f"{result['faithfulness_reason']}"
    )

    print("\n[UNSUPPORTED CLAIMS]")
    unsupported_claims = (
        result["unsupported_claims"]
    )

    if unsupported_claims:
        for claim in unsupported_claims:
            print(f"- {claim}")
    else:
        print("- 无")

    print("\n[LATENCY]")
    print(
        "Retrieval: "
        f"{result['retrieval_seconds']:.3f}s"
    )
    print(
        "Generation: "
        f"{result['generation_seconds']:.3f}s"
    )
    print(
        "Judge: "
        f"{result['judge_seconds']:.3f}s"
    )

    print("\n[RETRIEVED CHUNKS]")

    for chunk in result["retrieved_chunks"]:
        print(
            f"- rank={chunk['rank']} "
            f"score={chunk['score']:.4f} "
            f"source={chunk['source']}"
        )


def build_summary(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    汇总全部测试题的平均成绩。
    """
    total_cases = len(results)

    average_correctness = sum(
        result["correctness_score"]
        for result in results
    ) / total_cases

    average_relevance = sum(
        result["relevance_score"]
        for result in results
    ) / total_cases

    average_faithfulness = sum(
        result["faithfulness_score"]
        for result in results
    ) / total_cases

    passed_cases = sum(
        1
        for result in results
        if result["passed"]
    )

    pass_rate = (
        passed_cases / total_cases
    )

    average_retrieval_seconds = sum(
        result["retrieval_seconds"]
        for result in results
    ) / total_cases

    average_generation_seconds = sum(
        result["generation_seconds"]
        for result in results
    ) / total_cases

    average_judge_seconds = sum(
        result["judge_seconds"]
        for result in results
    ) / total_cases

    return {
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "pass_rate": pass_rate,
        "average_correctness": (
            average_correctness
        ),
        "average_relevance": (
            average_relevance
        ),
        "average_faithfulness": (
            average_faithfulness
        ),
        "average_retrieval_seconds": (
            average_retrieval_seconds
        ),
        "average_generation_seconds": (
            average_generation_seconds
        ),
        "average_judge_seconds": (
            average_judge_seconds
        ),
    }


def print_summary(
    summary: dict[str, Any],
) -> None:
    """
    打印总体评估结果。
    """
    print("\n" + "#" * 72)
    print("[ANSWER EVALUATION SUMMARY]")

    print(
        f"Total cases: "
        f"{summary['total_cases']}"
    )
    print(
        f"Passed cases: "
        f"{summary['passed_cases']}"
    )
    print(
        f"Pass rate: "
        f"{summary['pass_rate']:.2%}"
    )
    print(
        "Average Correctness: "
        f"{summary['average_correctness']:.2f}/5"
    )
    print(
        "Average Relevance: "
        f"{summary['average_relevance']:.2f}/5"
    )
    print(
        "Average Faithfulness: "
        f"{summary['average_faithfulness']:.2f}/5"
    )

    print("\n[AVERAGE LATENCY]")
    print(
        "Retrieval: "
        f"{summary['average_retrieval_seconds']:.3f}s"
    )
    print(
        "Generation: "
        f"{summary['average_generation_seconds']:.3f}s"
    )
    print(
        "Judge: "
        f"{summary['average_judge_seconds']:.3f}s"
    )


def save_results(
    results: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    """
    保存完整评估结果。
    """
    RESULT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "configuration": {
            "top_k": TOP_K,
            "pass_score": PASS_SCORE,
        },
        "summary": summary,
        "results": results,
    }

    with RESULT_PATH.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )


def main() -> None:
    """
    回答评估程序入口。
    """
    client = create_client()

    (
        answer_model,
        judge_model,
    ) = get_model_names()

    print(
        f"[ANSWER MODEL] {answer_model}"
    )
    print(
        f"[JUDGE MODEL] {judge_model}"
    )
    print(f"[TOP K] {TOP_K}")
    print(f"[PASS SCORE] {PASS_SCORE}")

    cases = load_eval_cases(
        CASES_PATH
    )

    if not cases:
        raise ValueError(
            "回答评估测试集为空。"
        )

    results: list[dict[str, Any]] = []

    for case in cases:
        result = evaluate_one_case(
            client=client,
            answer_model=answer_model,
            judge_model=judge_model,
            case=case,
            top_k=TOP_K,
        )

        results.append(result)
        print_case_result(result)

    summary = build_summary(results)

    print_summary(summary)

    save_results(
        results=results,
        summary=summary,
    )

    print(
        "\n[DONE] Evaluation results saved to:"
    )
    print(RESULT_PATH)


if __name__ == "__main__":
    main()