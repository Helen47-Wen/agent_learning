# Agentic RepoOps Assistant v0：Week 1 Design

## 1. 项目定位

Agentic RepoOps Assistant 是一个面向代码仓库、项目文档和日志的工程 Agent。

v0 版本的目标不是追求功能复杂，而是跑通最小 Agent 闭环：

```text
User Goal
-> RepoOpsState
-> LLM Planner
-> Structured Action
-> Tool Execution
-> Observation
-> State Update
-> Trace Logging
-> Finish
```

## 2. Week 1 已整合能力

v0 整合了 Day 01-06 的能力：

- `.env` API key 管理
- 大模型调用
- Prompt 设计
- Pydantic Schema
- Structured Action
- 只读文件工具
- Agent State
- ReAct Loop
- jsonl trace 日志

## 3. 当前支持的工具

v0 只支持只读工具：

```text
list_project_files
read_text_file
search_text
finish
```

暂时不支持：

```text
delete_file
write_file
run_shell_command
git_push
```

原因是：

```text
第一个版本应该优先保证可控、安全、可复盘。
写操作和命令执行需要 human-in-the-loop 和更严格的安全边界。
```

## 4. 当前 State 设计

RepoOpsState 包含：

```text
run_id
user_goal
repo_path
observations
status
risk_level
need_human_review
next_action_reason
final_answer
updated_at
```

其中：

```text
observations
```

用于保存工具返回结果。

```text
status
```

用于判断 Agent 是否继续运行。

```text
risk_level
```

用于后续接入安全控制和人工确认。

## 5. 当前 v0 的边界

v0 可以：

- 观察项目文件
- 读取文本文件
- 搜索关键词
- 让大模型选择下一步动作
- 更新状态
- 记录 trace

v0 还不能：

- 自动修复代码
- 自动执行 shell 命令
- 自动提交 Git
- 判断复杂 bug 根因
- 做 RAG 检索
- 做系统性 eval

这些能力会在后续天数中逐步加入。

## 6. 后续升级路线

后续可以逐步升级：

```text
Day 08：RAG 基础
Day 09：日志诊断 Agent
Day 10：Reflection / Reflexion
Day 11：Repair Planner
Day 12：安全命令执行
Day 13：Human-in-the-loop
Day 14：RepoOps Assistant v1
```

## 7. AUV Fluent Agent 映射

AUV Fluent Simulation Agent 也可以复用相同架构：

```text
User Goal
-> AUVState
-> LLM Planner
-> Simulation Tool
-> Observation
-> Stage Update
-> Error Diagnosis
-> Human Review or Continue
```

对应工具可以是：

```text
check_project_files
detect_simulation_stage
read_fluent_log
check_mesh_quality
validate_solver_result
export_report_summary
```

## 8. v0 面试表达

可以这样描述：

我实现了一个 RepoOps Assistant v0。它不是简单调用一次大模型，而是把任务拆成 State、LLM Planner、Structured Action、Tool Execution、Observation 和 Trace Logging。模型只负责选择下一步动作，Python 工具层负责真正执行，并用 Pydantic 校验结构化输出，保证 Agent Loop 可控、可复盘、可扩展。