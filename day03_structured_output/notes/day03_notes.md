# Day 03：结构化输出与 Pydantic 校验

## 1. 今日学习目标

今天学习如何让 LLM 输出程序可解析、可校验、可进入 Agent 状态机的数据。

核心目标：

- 理解符号规划 Agent 的 State / Goal / Action / Precondition / Effect / Plan
- 理解结构化输出的必要性
- 使用 Pydantic 定义输出 schema
- 实现 RepoOps Assistant 的 Issue Triage 模块

## 2. 符号规划 Agent 核心概念

符号规划 Agent 可以理解为：

当前状态 State
→ 目标状态 Goal
→ 可执行动作 Action
→ 动作前提 Precondition
→ 动作效果 Effect
→ 动作序列 Plan

Agent 的任务是从当前状态出发，选择满足前提条件的动作，逐步达到目标状态。

## 3. RepoOps Assistant 中的映射

以 Issue Triage 为例：

- State：当前 Issue 标题、正文、错误日志、仓库背景
- Goal：把 Issue 分流到正确处理路径
- Action：请求补充信息、创建修复计划、分配维护者、安全升级
- Precondition：Issue 信息足够、错误日志明确、问题类型可判断
- Effect：Issue 被分类、打标签、确定优先级和下一步动作
- Plan：后续进入修复、文档更新或人工复核流程

## 4. 为什么需要结构化输出？

自然语言输出不稳定，程序难以解析。

Agent 系统需要字段化结果，例如：

- issue_type
- priority
- next_action
- risk_level
- need_human_review
- reason

这些字段可以进入状态机、工具调用、评估脚本和日志系统。

## 5. 为什么需要 Pydantic？

LLM 即使被要求输出 JSON，也可能出现：

- 字段缺失
- 字段名错误
- 类型错误
- 枚举值不合法
- JSON 外夹杂解释文字
- 幻觉不存在的信息

Pydantic 可以在模型输出进入程序状态前进行校验。

## 6. 今日项目进展

今天为 Agentic RepoOps Assistant 补充了：

- 项目 README
- System Prompt
- Issue Triage Prompt
- IssueTriageDecision schema
- 可运行的 Issue Triage Parser
- JSONL 调用日志

## 7. 和 AUV / Fluent 项目的关系

AUV / Fluent 阶段判断和 Issue Triage 本质类似：

都是把非结构化上下文转换为结构化决策。

Issue Triage 输出 issue_type 和 next_action。
AUV Stage Detector 输出 current_stage 和 next_action。

后续可以将今天的结构化输出模式迁移到仿真阶段判断、日志诊断和结果校验中。

## 8. 今日结论

结构化输出是 LLM Agent 工程化的第一道接口。
Pydantic 校验是防止模型不稳定输出污染 Agent State 的关键边界。