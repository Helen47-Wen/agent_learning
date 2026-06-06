# Day 06 学习笔记：ReAct Loop

## 1. ReAct 是什么

ReAct 是 Reasoning + Acting。

它让 Agent 在任务执行过程中不断：

1. 观察当前状态
2. 让大模型判断下一步动作
3. 调用工具
4. 获取观察结果
5. 更新内部状态
6. 判断继续还是结束

工程化后，可以写成：

```text
State -> LLM Planner -> Action -> Tool -> Observation -> State Update
```

## 2. 为什么 ReAct 很重要

普通 LLM 调用通常是：

```text
输入 prompt -> 输出答案
```

而 Agent 更像是：

```text
输入目标
-> 多次观察
-> 多次调用工具
-> 多次更新状态
-> 最终完成任务
```

所以 ReAct 是从“问答模型”走向“任务执行系统”的关键一步。

## 3. 工程化 ReAct 不一定保存完整 Thought

早期 ReAct prompt 经常写成：

```text
Thought:
Action:
Observation:
```

但在真实工程中，不建议依赖模型自由输出长篇 Thought。

更推荐记录：

```text
action_name
action_args
observation
state_update
next_action_reason
```

也就是说，记录可审计的决策摘要，而不是保存不可控的长篇思维过程。

## 4. ReAct 和 Tool Calling 的关系

Tool Calling 是 API 能力。

ReAct Loop 是系统流程。

一个成熟 Agent 通常是：

```text
ReAct Loop
+ Tool Calling
+ State
+ Pydantic Validation
+ Logging
+ Retry
+ Human Review
```

## 5. Day 06 的 RepoOps Assistant 最小循环

今天 RepoOps Assistant 的最小循环可以设计成：

```text
list_project_files
-> read_text_file
-> search_text
-> finish
```

含义是：

```text
先观察项目结构
再读取关键文件
必要时搜索关键词
最后总结并结束
```

## 6. Day 06 的 AUV Fluent Agent 映射

AUV Fluent Agent 中也可以用同样的结构：

```text
check_project_files
-> detect_simulation_stage
-> read_latest_log
-> diagnose_error
-> suggest_next_action
```

例如：

```text
如果发现 msh.h5 已存在，但是 cas.h5 不存在，
说明大概率已经完成 Meshing，但还没有完成 Solver。
下一步应该进入 Fluent Solver 阶段。
```

## 7. 当前主流 Agent 与 ReAct 的关系

现在很多 Agent 框架不一定显式写出：

```text
Thought -> Action -> Observation
```

但底层仍然离不开类似的循环：

```text
State
-> Tool Call
-> Tool Result
-> State Update
-> Next Step
```

区别是，现代 Agent 更强调：

```text
结构化输出
严格工具参数
状态管理
日志追踪
人工确认
失败恢复
评估体系
```

因此，ReAct 的思想没有过时，只是从 prompt pattern 发展成了更工程化的 Agent runtime。

## 8. 我今天要记住的一句话

ReAct 不是让模型随便多想几步，而是让 Agent 在工具反馈的基础上持续更新状态并选择下一步动作。