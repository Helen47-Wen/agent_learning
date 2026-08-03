# RepoOps Assistant：RAG v0 Design

## 1. 目标

RAG v0 的目标是让 RepoOps Assistant 能基于项目文件回答问题，而不是只依赖模型自己的记忆或用户临时描述。

## 2. 当前流程

项目文件
-> 文档切分
-> qwen3-embedding:8b 生成 embedding
-> 保存 jsonl 索引
-> 用户问题生成 embedding
-> cosine similarity 检索 top_k
-> 构造 retrieved context
-> 聊天模型生成回答
-> 保存 QA 日志