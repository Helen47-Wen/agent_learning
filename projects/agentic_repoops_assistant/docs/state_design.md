# State Design for Agentic RepoOps Assistant

## 1. 为什么需要 State？

Agentic RepoOps Assistant 不是一次性问答系统，而是一个多步骤工程 Agent。

它需要在执行过程中维护：

- 当前项目事实
- 用户目标
- 已执行工具结果
- Issue 判断结果
- 风险等级
- 是否需要人工确认
- 下一步动作

这些信息共同组成 Agent State。

## 2. BDI 映射

### Belief

Agent 当前知道的事实，例如：

- 项目根目录
- 已发现文件
- 是否存在 README
- 是否存在 requirements.txt
- 最近日志摘要
- 工具观察结果

### Desire

Agent 当前希望达成的目标，例如：

- 帮助用户理解项目状态
- 分类 Issue
- 诊断错误
- 生成修复计划

### Intention

Agent 当前承诺执行的下一步动作，例如：

- scan_project
- triage_issue
- diagnose_log
- create_fix_plan
- ask_human_review
- final_answer

## 3. State 与 Context 的区别

State 是程序内部维护的结构化数据。

Context 是本次发给模型看的信息。

不能把所有 State、所有日志、所有历史都直接塞进 Context，应该根据任务构造精简上下文。

## 4. 当前 State 字段

当前 v0 State 包括：

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

## 5. 后续演进

后续会把当前 State 接入：

- Tool Calling
- RAG
- ReAct Loop
- LangGraph StateGraph
- Human-in-the-loop
- Evaluation
- Trace Logging