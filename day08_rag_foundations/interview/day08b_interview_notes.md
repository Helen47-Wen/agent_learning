# Day 08-B 面试笔记：项目文件 RAG

## Q1：你今天实现了什么？

我把 RAG 从手写 DOCUMENTS demo 升级成了项目文件 RAG。

它可以扫描项目目录，把 README、docs、notes 和代码文件切成 chunk，调用本地部署的 qwen3-embedding:8b 生成 embedding，并保存到本地 jsonl 索引中。

用户提问时，系统会先检索相关 chunk，再把检索结果交给大模型回答。

## Q2：为什么要把建库和问答分开？

因为项目文件 embedding 不应该每次提问都重新计算。

建库阶段负责：

文档 -> chunk -> embedding -> index

问答阶段负责：

question -> embedding -> retrieve -> answer

这样效率更高，也更接近真实 RAG 系统。

## Q3：为什么不用一开始就上向量数据库？

因为当前阶段的目标是理解 RAG 主流程。

jsonl 索引足够表达：

chunk_id
source_path
text
embedding

等流程跑通后，再接 FAISS、Chroma、LanceDB 或 pgvector。

## Q4：这个 RAG 和 Agent 有什么关系？

RAG 可以作为 Agent 的一个工具。

例如 RepoOps Assistant 的 Planner 可以选择：

retrieve_project_knowledge

然后基于检索结果继续分析项目状态、诊断日志或规划修复步骤。

## Q5：如何映射到 AUV Fluent Agent？

AUV Fluent Agent 可以把 Fluent 日志、Meshing 日志、网格质量报告、残差记录和历史修复方案建立成知识库。

当新错误出现时，Agent 可以先检索历史案例，再判断错误原因和下一步排查方向。