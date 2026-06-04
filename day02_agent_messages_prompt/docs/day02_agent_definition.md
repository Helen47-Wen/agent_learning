# Day 02：Agent 定义与 Messages / Prompt 结构

## 1. Agent 是什么？

Agent 是一个能够根据目标感知环境、维护状态、做出决策、执行动作并根据反馈调整行为的系统。

工程化表达：

Agent = LLM + State + Tools + Planning + Execution + Feedback + Evaluation

## 2. LLM 和 Agent 的区别

LLM 更像大脑，主要负责理解和生成。
Agent 是系统，除了 LLM，还包括状态、工具、动作和反馈闭环。

## 3. Agent 和普通脚本的区别

普通脚本按固定流程执行。
Agent 会根据当前状态和反馈决定下一步，并能处理异常、请求人工确认、记录执行过程。

## 4. system / user / assistant 的区别

system：长期规则和角色约束  
user：当前任务  
assistant：历史上下文  

## 5. 这和 AUV / Fluent 项目的关系

AUV / Fluent 自动化项目已经有工具基础，但要变成 Agent，还需要：

- 状态管理
- 阶段判断
- 工具调用决策
- 日志解析
- 错误诊断
- 结果校验
- 人工确认机制
- 评估指标