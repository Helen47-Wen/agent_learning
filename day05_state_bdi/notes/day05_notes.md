# Day 05：BDI 与 Agent State 设计

## 1. 今日目标

今天学习 BDI 思想和 Agent State 设计，并为 Agentic RepoOps Assistant 实现第一版状态结构。

## 2. BDI 是什么？

BDI 分别是：

- Belief：Agent 当前知道或相信的事实
- Desire：Agent 想要达成的目标
- Intention：Agent 当前决定执行的下一步动作

通俗理解：

知道什么 → 想完成什么 → 准备做什么

## 3. RepoOps Assistant 中的 BDI

### Belief

- 项目根目录
- 已发现文件
- 是否存在 README
- 是否存在 requirements.txt
- 最近日志
- 工具观察结果

### Desire

- 分析项目状态
- 分类 Issue
- 诊断错误
- 生成修复计划

### Intention

- scan_project
- read_readme
- triage_issue
- diagnose_log
- create_fix_plan
- ask_human_review
- final_answer

## 4. State / Memory / Context / RAG 区别

State：当前任务运行状态  
Memory：跨任务或长期保存的信息  
Context：本次传给模型看的内容  
RAG：从外部资料中检索相关信息的方法  

## 5. 为什么 State 重要？

没有 State 的 Agent 容易出现：

- 重复做同一件事
- 忘记前面工具结果
- 无法判断下一步
- 无法恢复执行
- 无法调试
- 无法评估

## 6. 今天的代码实现

今天实现了：

- RepoSnapshot
- IssueTriageResult
- ToolObservation
- RepoOpsState
- update_belief_from_files
- apply_issue_triage_result
- decide_next_intention
- build_model_context_from_state

## 7. 今日结论

Agent State 是连接 Prompt、Tool Calling、RAG、LangGraph 和 Evaluation 的中心结构。

结构化 State 让 Agent 从“临时回答”变成“可持续推进任务的工程系统”。