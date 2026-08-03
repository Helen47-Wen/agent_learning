# Day 07 学习笔记：RepoOps Assistant v0

## 1. 今天整合了什么？

今天把前 6 天内容整合成一个最小 Agent 项目：

```text
RepoOps Assistant v0
```

它包含：

- LLM API
- Prompt
- Structured Action
- Pydantic 校验
- 文件工具
- State
- ReAct Loop
- jsonl trace

## 2. v0 为什么重要？

因为它说明 Agent 不是单次问答，而是一个循环系统。

普通 LLM 调用是：

```text
输入 -> 输出
```

Agent Loop 是：

```text
目标
-> 状态
-> 模型决策
-> 工具执行
-> 观察结果
-> 状态更新
-> 下一步
```

## 3. 模型负责什么？

模型负责：

```text
根据当前 State 和 Observation，判断下一步该做什么。
```

例如：

```json
{
  "action_name": "read_text_file",
  "action_args": {
    "path": "README.md"
  },
  "reason": "README usually contains the project overview."
}
```

## 4. Python 负责什么？

Python 负责：

- 校验模型输出
- 执行工具
- 捕获异常
- 限制路径
- 更新状态
- 写日志
- 控制最大循环次数

也就是说：

```text
模型负责决策
程序负责执行
```

## 5. 为什么要有 Pydantic？

Pydantic 用来保证模型输出符合预期结构。

如果模型乱输出：

```text
我觉得应该看看 README
```

程序不好执行。

如果模型输出：

```json
{
  "action_name": "read_text_file",
  "action_args": {
    "path": "README.md"
  },
  "reason": "Read project overview."
}
```

程序就可以稳定解析并执行。

## 6. 为什么要有 max_steps？

Agent 有可能陷入循环，例如：

```text
读文件
-> 搜索
-> 再读文件
-> 再搜索
```

所以必须限制最大步数。

v0 中：

```text
max_steps = 6
```

表示最多执行 6 轮。

## 7. 为什么先只做只读工具？

因为写文件、删文件、执行命令都有风险。

v0 阶段只做：

```text
list_project_files
read_text_file
search_text
```

这样更安全，也更适合初期验证架构。

## 8. 今天要记住的一句话

第 1 周的核心成果不是写了很多功能，而是跑通了一个最小可控 Agent 闭环：

```text
State -> LLM Planner -> Action -> Tool -> Observation -> State Update -> Trace
```