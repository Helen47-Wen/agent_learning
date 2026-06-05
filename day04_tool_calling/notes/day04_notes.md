# Day 04：Tool Calling 与工具层设计

## 1. 今日主题

今天学习 Tool Calling，并为 Agentic RepoOps Assistant 实现第一版只读工具层。

## 2. Tool Calling 是什么？

Tool Calling 是让模型根据任务选择外部工具，并生成工具参数。

模型不直接执行工具，真实执行由应用程序完成。

基本流程：

用户目标
→ LLM 选择工具
→ 生成 tool_name 和 tool_args
→ 程序校验参数
→ 执行工具
→ 返回 ToolResult
→ Agent 根据结果继续下一步

## 3. 为什么 Agent 需要工具？

LLM 本身不能可靠知道当前文件、日志、数据库或外部系统状态。

Agent 要完成真实任务，必须通过工具获取外部世界的信息或执行动作。

## 4. Tool Schema 的作用

Tool Schema 用来告诉模型：

- 有哪些工具
- 工具什么时候使用
- 工具需要哪些参数
- 参数类型是什么
- 工具边界是什么

## 5. ToolResult 的作用

ToolResult 是工具返回给 Agent 的标准结构。

它让后续 Agent 可以稳定读取：

- 工具是否成功
- 返回了什么数据
- 是否有错误
- 错误类型是什么
- 执行耗时是多少

## 6. 今天实现的工具

今天实现了四个只读工具：

- list_project_files
- read_text_file
- search_text
- read_recent_log

它们都是低风险工具，适合作为 RepoOps Assistant 的第一层能力。

## 7. 当前主流 API 实现方式

当前主流模型服务通常支持原生 Tool Calling 或 Function Calling。

工程上可以采用两层策略：

1. 有原生 Tool Calling 时，优先使用 API 提供的工具调用能力
2. 为了兼容不同模型，也可以使用结构化 JSON 输出模拟工具调用

无论哪种方式，工具参数都应该本地校验，工具结果都应该结构化。

## 8. 今日结论

Tool Calling 让 LLM 从“只会回答”变成“可以请求外部能力”。

但可靠 Agent 的关键不是让模型随便调用工具，而是：

- 工具边界清晰
- 参数可校验
- 执行可控制
- 结果可追踪
- 高风险动作有人类确认