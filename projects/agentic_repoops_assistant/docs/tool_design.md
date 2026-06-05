# Tool Design for Agentic RepoOps Assistant

## 1. Tool Calling 的定位

Tool Calling 的核心不是让模型直接执行操作，而是让模型决定应该调用哪个工具，并生成结构化参数。

真实执行由 Python 程序完成。

## 2. 当前工具层 v0

当前 v0 只支持只读工具：

- list_project_files：列出项目文件
- read_text_file：读取文本文件
- search_text：搜索关键词
- read_recent_log：读取日志最后若干行

## 3. 工具设计原则

### 3.1 工具必须有清晰边界

每个工具只做一类事情，不要把多个职责混在一起。

### 3.2 工具参数必须可校验

模型生成的参数不能直接信任，需要用 schema 或函数内部逻辑校验。

### 3.3 工具返回必须结构化

所有工具统一返回 ToolResult，包括：

- tool_name
- status
- message
- data
- error_type
- elapsed_seconds

### 3.4 高风险工具必须人工确认

后续涉及以下操作时，必须加 human-in-the-loop：

- 删除文件
- 覆盖文件
- 修改代码
- 执行命令
- git push
- 运行长时间任务

## 4. 后续扩展

下一步可以增加：

- dependency_checker
- test_runner
- log_diagnoser
- repair_planner
- safe_command_executor