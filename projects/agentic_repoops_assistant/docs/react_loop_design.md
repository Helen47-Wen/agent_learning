# Agentic RepoOps Assistant：ReAct Loop Design

## 1. 目标

为 Agentic RepoOps Assistant 增加观察-行动循环，使它不只是一次性分析文本，而是可以持续读取项目文件、更新状态、选择下一步动作。

## 2. 核心 Loop

```text
User Goal
-> RepoOpsState
-> LLM Planner
-> Structured Action
-> Tool Execution
-> ToolResult / Observation
-> State Update
-> Stop or Continue
```

## 3. 当前支持的动作

当前最小版本建议支持：

- list_project_files
- read_text_file
- search_text
- finish

后续可以扩展：

- read_recent_log
- summarize_project_status
- triage_issue
- propose_repair_plan
- request_human_review

## 4. 当前建议状态字段

RepoOpsState 至少包含：

- run_id
- user_goal
- belief
- desire
- intention
- issue_triage
- observations
- risk_level
- need_human_review
- status
- next_action_reason
- updated_at

## 5. 工程设计原则

### 5.1 模型只负责决策，不直接执行动作

模型负责生成类似这样的结构化动作：

```json
{
  "action_name": "read_text_file",
  "action_args": {
    "path": "README.md",
    "max_chars": 3000
  }
}
```

真正的文件读取、搜索、日志分析必须由 Python 工具层执行。

### 5.2 Action 必须结构化

不要让模型自由输出：

```text
我觉得下一步应该读取 README.md
```

而是让模型输出结构化结果：

```json
{
  "action_name": "read_text_file",
  "action_args": {
    "path": "README.md"
  }
}
```

这样 Python 才能稳定解析、校验和执行。

### 5.3 Observation 必须结构化

工具执行结果也不要随便拼成自然语言。

推荐统一格式：

```json
{
  "tool_name": "read_text_file",
  "success": true,
  "data": "...",
  "error": null
}
```

### 5.4 State Update 必须可审计

每一步都应该记录：

```text
当前 action
工具参数
工具结果
状态变化
下一步原因
```

这样后续才能 debug、评估、复盘和面试展示。

## 6. 安全边界

RepoOps Assistant 早期只允许只读工具：

```text
list_project_files
read_text_file
search_text
read_recent_log
```

不要一开始就允许：

```text
delete_file
run_shell_command
git_push
```

如果后续引入写操作，必须加入：

```text
human-in-the-loop
path allowlist
risk_level
approval_required
execution sandbox
```

## 7. 后续升级方向

后续可以逐步升级为：

- 用 Structured Outputs 生成 ReactAction
- 用 Pydantic 校验 action
- 用 retry / fallback 处理模型输出异常
- 增加 human-in-the-loop
- 增加 tracing / observability
- 迁移到 LangGraph StateGraph
- 增加 eval harness 测试 Agent 是否稳定
- 接入 AUV Fluent Agent 的阶段判断和日志诊断能力