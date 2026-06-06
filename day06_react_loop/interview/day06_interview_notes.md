# Day 06 面试笔记：ReAct Loop

## Q1：ReAct 是什么？

ReAct 是 Reasoning and Acting 的结合。

它让 Agent 在解决任务时，不只是内部推理，而是可以边推理边调用工具，利用外部观察结果修正下一步动作。

工程上，我会把它理解为：

```text
State -> Action -> Observation -> State Update
```

## Q2：ReAct 和 CoT 有什么区别？

CoT 主要强调模型内部的多步推理。

ReAct 强调推理和行动交替进行：

```text
Reason -> Act -> Observe -> Reason -> Act -> Observe
```

所以 ReAct 更适合需要查文件、查数据库、调用 API、执行命令的工程任务。

## Q3：ReAct 和 Tool Calling 有什么区别？

Tool Calling 是模型调用工具的机制。

ReAct 是一种 Agent 控制循环。

Tool Calling 可以作为 ReAct 中 Action 的实现方式，但 Tool Calling 本身不等于完整 Agent。

可以这样说：

```text
Tool Calling 解决“怎么让模型调用工具”。
ReAct Loop 解决“什么时候调用工具、调用后怎么继续”。
```

## Q4：为什么 Agent 需要 State？

因为 Agent 每一步都需要知道：

- 目标是什么
- 已经观察到了什么
- 当前准备做什么
- 上一步工具结果是什么
- 是否需要人工确认
- 是否已经完成任务

没有 State，Agent 就只是一次性问答，不是可靠的任务执行系统。

## Q5：为什么工具执行不能交给模型？

模型只负责生成工具调用意图，例如：

```text
我要读取 README.md
```

真正执行必须由程序完成，因为程序可以：

- 校验参数
- 限制路径
- 捕获异常
- 记录日志
- 阻止危险操作

这也是 Agent 安全性的基础。

## Q6：ReAct 在 RepoOps Assistant 中怎么体现？

RepoOps Assistant 可以通过 ReAct Loop：

1. 观察项目目录
2. 读取 README / docs / logs / issues
3. 搜索错误信息
4. 生成修复建议
5. 判断是否需要人工确认
6. 输出可审计 trace

## Q7：ReAct 在 AUV Fluent Simulation Agent 中怎么体现？

AUV Fluent Agent 可以通过 ReAct Loop：

1. 检查 SolidWorks / SpaceClaim / Fluent Meshing / Solver 文件
2. 判断当前处于哪个阶段
3. 读取日志
4. 识别错误
5. 选择重跑网格、修改边界条件、导出结果等动作
6. 更新仿真状态
7. 必要时请求人工确认

## Q8：面试中怎么高级一点回答？

可以这样说：

我理解的 ReAct 不只是 prompt 里的 Thought / Action / Observation，而是一种 Agent 控制循环。工程实现时，我会把 Action、Observation、State Update 都结构化，用 Pydantic 或 JSON Schema 校验，并且通过日志记录每一步 trace。模型只负责决策，Python 程序负责工具执行和安全控制。后续可以用 LangGraph 把这个循环升级成状态图，支持条件路由、人工确认和失败恢复。

## Q9：真实 Agent 现在还是 ReAct 这样运行吗？

可以这样回答：

真实 Agent 不一定显式写出 Thought / Action / Observation，但底层仍然离不开类似 ReAct 的循环。现在主流框架通常把它封装成 tools、state、trace、guardrails、workflow graph 和 human-in-the-loop。也就是说，ReAct 的思想仍然存在，只是从 prompt pattern 发展成了工程化 Agent runtime。