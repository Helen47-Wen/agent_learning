# Day 07 面试笔记：RepoOps Assistant v0

## Q1：你第 1 周做出了什么？

我完成了一个最小版 RepoOps Assistant v0。

它可以根据用户目标观察项目文件，调用只读工具读取文件或搜索文本，并把每一步结果记录到 Agent State 和 trace 日志中。

它的核心流程是：

```text
User Goal
-> State
-> LLM Planner
-> Structured Action
-> Tool Execution
-> Observation
-> State Update
-> Trace Logging
```

## Q2：这个项目和普通 LLM 调用有什么区别？

普通 LLM 调用通常是一次输入、一次输出。

RepoOps Assistant v0 是一个 Agent Loop：

```text
它会多次观察、多次调用工具、多次更新状态，直到完成任务或达到最大步数。
```

## Q3：模型在这个系统里负责什么？

模型负责规划下一步动作。

例如：

```text
当前没有观察结果，所以先 list_project_files。
发现 README.md 后，再 read_text_file。
信息足够后，选择 finish。
```

模型不直接执行工具。

## Q4：Python 程序负责什么？

Python 程序负责：

- 校验模型输出
- 执行工具函数
- 限制路径范围
- 捕获工具异常
- 更新 State
- 记录 jsonl trace
- 控制 max_steps

这保证了 Agent 的可控性和安全性。

## Q5：为什么需要结构化输出？

如果模型输出自然语言：

```text
我想看看 README.md。
```

程序很难稳定执行。

如果模型输出结构化 Action：

```json
{
  "action_name": "read_text_file",
  "action_args": {
    "path": "README.md"
  },
  "reason": "README contains project overview."
}
```

程序就可以解析、校验、执行。

## Q6：为什么 v0 只做只读工具？

因为第一个版本应该优先保证安全和可复盘。

读文件、搜索文本风险较低。

写文件、执行命令、提交 Git 都属于高风险动作，需要后续加入：

- human-in-the-loop
- path allowlist
- risk_level
- approval_required
- sandbox

## Q7：这个项目后续如何升级？

后续可以升级为：

```text
RAG 文档检索
日志诊断
错误修复规划
安全命令执行
Human-in-the-loop
LangGraph 工作流
Agent eval harness
Tracing / observability
```

## Q8：如何映射到 AUV Fluent Agent？

RepoOps Assistant v0 的架构可以迁移到 AUV Fluent Agent：

```text
RepoOpsState -> AUVState
文件工具 -> 仿真文件检查工具
日志搜索 -> Fluent 日志诊断
Project status -> Simulation stage status
Repair plan -> Simulation error recovery plan
```

例如 AUV Agent 可以：

```text
检查 mesh 文件是否存在
读取 Fluent transcript
判断是否收敛
检查残差和网格质量
决定是否需要人工确认
```

## Q9：面试中怎么总结这个 v0？

可以这样说：

我第 1 周实现了一个最小可运行的 RepoOps Assistant v0。它不是单次调用大模型，而是一个具备 State、LLM Planner、Structured Action、Tool Execution、Observation 和 Trace Logging 的 Agent Loop。模型负责选择下一步动作，Python 负责实际工具执行和安全控制。这个架构后续可以平滑升级到 LangGraph、RAG、日志诊断和 Human-in-the-loop。