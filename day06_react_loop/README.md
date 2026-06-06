# Day 06：ReAct Loop

## 1. 今日主题

今天学习 ReAct Loop，并把前面已经学过的工具层、State 和大模型调用连接起来。

今天的重点不是再模拟一个假 Agent，而是理解真实 Agent 的最小执行循环：

```text
State
-> LLM Planner
-> Structured Action
-> Tool Execution
-> Observation
-> State Update
-> Continue / Finish
```

## 2. ReAct 是什么

ReAct = Reasoning + Acting。

工程化理解：

```text
Observe -> Decide -> Act -> Observe -> Update State -> Continue / Finish
```

也就是说，Agent 不是一次性回答完，而是会根据当前状态决定下一步动作，调用工具，拿到工具结果，然后继续判断。

## 3. ReAct 和 CoT 的区别

CoT 主要强调模型内部的多步推理。

ReAct 不只是推理，而是会在推理过程中调用外部工具，拿到 Observation，再继续决定下一步。

简单理解：

```text
CoT：
模型自己想清楚，然后回答。

ReAct：
模型边判断边行动，行动后根据外部结果继续调整。
```

## 4. ReAct 和 Tool Calling 的区别

Tool Calling 是模型调用工具的 API 能力。

ReAct Loop 是围绕目标、状态、工具、观察结果组织起来的执行循环。

关系可以理解为：

```text
Tool Calling 是能力
ReAct Loop 是流程
State 是上下文和任务状态
Observation 是工具反馈
```

## 5. 今日代码文件

```text
schemas/react_step_schema.py
examples/01_llm_react_loop.py
logs/.gitkeep
```

其中：

```text
react_step_schema.py
```

负责定义 ReAct 每一步的结构化数据。

```text
01_llm_react_loop.py
```

负责让大模型根据当前 State 选择下一步工具，并由 Python 执行工具、更新 State、记录日志。

## 6. 运行命令

在项目根目录运行：

```powershell
python day06_react_loop\examples\01_llm_react_loop.py
```

## 7. RepoOps Assistant 映射

RepoOps Assistant 的 ReAct Loop：

```text
观察项目文件
-> LLM 判断下一步该读取哪个文件或搜索什么内容
-> 调用文件工具
-> 得到 Observation
-> 更新 RepoOpsState
-> 继续诊断或结束
```

例如：

```text
list_project_files
-> read_text_file
-> search_text
-> finish
```

## 8. AUV Fluent Agent 映射

AUV Fluent Agent 的 ReAct Loop：

```text
观察仿真项目目录
-> 判断当前处于 SolidWorks / SpaceClaim / Meshing / Solver 哪个阶段
-> 读取 Fluent 或 Meshing 日志
-> 判断是否有错误
-> 选择下一步动作
-> 更新 AUVState
-> 继续执行或请求人工确认
```

例如：

```text
check_project_files
-> detect_simulation_stage
-> read_fluent_log
-> diagnose_error
-> suggest_next_action
```

## 9. 今日重点

今天真正要掌握的是：

```text
1. Agent 不是一次性问答，而是循环执行系统。
2. LLM 负责决策，不负责真正执行工具。
3. Python 负责工具执行、错误捕获、日志记录。
4. State 保存当前 Agent 已知信息。
5. Observation 是工具执行后的结果。
6. max_steps 用来防止 Agent 无限循环。
```