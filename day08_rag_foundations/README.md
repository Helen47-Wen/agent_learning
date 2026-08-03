# Day 08-A：RAG 最小入门

我已经跑通了一个混合式 RAG demo：
使用本地部署的 qwen3-embedding:8b 做 embedding 检索，
使用云端大模型做最终回答。
这样既能理解标准 RAG 的检索流程，又能保持较好的生成速度。

retrieved_documents = retrieve_relevant_documents(
        question=question,
        top_k=1,
    )
这里的k调节影响选择的范围
top_k: int = 2 是 Python 函数参数的定义：
top_k：参数名，表示“取最相关的前 K 条资料”
: int：类型提示，表示它应该是整数
= 2：默认值是 2

## 1. 今天学什么？

今天学习 RAG 的最小闭环。

RAG = Retrieval-Augmented Generation。

中文可以理解为：

```text
检索增强生成
```

最简单理解：

```text
先查资料，再让大模型基于资料回答。
```

## 2. 为什么需要 RAG？

大模型本身不一定知道你的本地项目文件、日志、历史记录。

如果直接问模型：

```text
我的 RepoOps Assistant 项目现在实现了什么？
```

模型可能会猜。

RAG 的做法是：

```text
先从项目资料中检索相关片段，
再把这些片段交给大模型回答。
```

## 3. RAG 的最小流程

```text
Documents
-> Embeddings
-> Query Embedding
-> Similarity Search
-> Retrieved Context
-> LLM Answer
```

## 4. 今天的代码文件

```text
examples/01_min_rag_demo.py
```

它会做 5 件事：

1. 准备几段示例资料
2. 给每段资料生成 embedding
3. 给用户问题生成 embedding
4. 用相似度找出最相关资料
5. 把资料交给大模型回答

## 5. 运行命令

在项目根目录运行：

```powershell
python day08_rag_foundations\examples\01_min_rag_demo.py
```

## 6. 今天要记住的一句话

RAG 不是让模型记住所有资料，而是在回答前动态找出最相关的资料。