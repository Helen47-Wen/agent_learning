# Day 04 面试笔记：Tool Calling

## Q1：Tool Calling 的本质是什么？

Tool Calling 的本质是让模型根据任务决定调用哪个外部工具，并生成结构化参数。

模型不直接执行工具，工具由应用程序真实执行。

---

## Q2：为什么 LLM Agent 需要工具？

因为 LLM 本身只能基于上下文生成回答，不能可靠知道外部世界的当前状态。

如果 Agent 需要读取文件、查询数据库、运行测试、检索文档或调用 API，就必须通过工具完成。

---

## Q3：Tool Calling 和 Structured Output 有什么区别？

Structured Output 主要控制模型最终回答的格式。

Tool Calling 主要控制模型请求外部动作的方式。

简单理解：

- Structured Output：模型输出一个结构化结论
- Tool Calling：模型请求程序执行一个工具

---

## Q4：为什么工具参数不能直接信任？

因为模型可能生成错误参数，例如：

- 字段缺失
- 类型错误
- 路径错误
- 工具名不存在
- 参数越权
- 请求高风险操作

所以工具参数必须经过 schema 校验和安全检查。

---

## Q5：如何设计一个好的工具？

一个好的工具应该具备：

- 名称清晰
- 职责单一
- 描述明确
- 参数结构简单
- 返回结构稳定
- 错误类型明确
- 有权限控制

---

## Q6：ToolResult 为什么重要？

ToolResult 让工具结果可以进入后续 Agent 流程。

它应该包含：

- tool_name
- status
- message
- data
- error_type
- elapsed_seconds

这样 Agent 才能根据工具结果继续规划、重试、诊断或结束任务。

---

## Q7：在 RepoOps Assistant 中，Tool Calling 怎么体现？

RepoOps Assistant 可以通过工具完成：

- 列出项目文件
- 读取 README
- 搜索关键词
- 读取错误日志
- 检查依赖
- 运行测试
- 生成修复计划

今天只实现低风险只读工具，为后续日志诊断、RAG 和 LangGraph 工作流做准备。

---

## Q8：在 AUV / Fluent Agent 中，Tool Calling 怎么体现？

AUV / Fluent Agent 可以把以下操作封装成工具：

- 检查 SolidWorks 文件
- 检查 SpaceClaim 输出
- 检查 mesh 文件
- 读取 Fluent 日志
- 解析求解结果
- 校验 force.csv 和云图
- dry-run 运行 solver 脚本

高风险操作，例如覆盖网格、重跑 solver、修改原始模型，必须人工确认。