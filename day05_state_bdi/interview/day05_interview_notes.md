# Day 05 面试笔记：BDI 与 Agent State

## Q1：什么是 BDI Agent？

BDI 指 Belief、Desire、Intention。

- Belief：Agent 当前知道的事实
- Desire：Agent 想要达成的目标
- Intention：Agent 当前承诺执行的下一步动作

它可以帮助我们把 Agent 的决策过程结构化。

---

## Q2：Agent State 是什么？

Agent State 是 Agent 在执行任务过程中维护的结构化状态。

它通常包括：

- 用户目标
- 当前阶段
- 已知事实
- 工具结果
- 检索结果
- 错误信息
- 风险等级
- 下一步动作
- 是否需要人工确认

---

## Q3：State 和 Prompt 有什么区别？

Prompt 是发给模型的一段输入。

State 是程序内部维护的结构化数据。

Prompt 可以由 State 动态生成，但 State 不应该完全依赖 Prompt 保存。

---

## Q4：State 和 Memory 有什么区别？

State 更偏当前任务运行过程中的短期状态。

Memory 更偏跨任务、跨会话保存的长期信息。

例如：

- State：本次 run 中已经扫描到 README.md
- Memory：用户长期偏好使用 Windows PowerShell

---

## Q5：State 和 RAG 有什么区别？

State 是当前任务状态。

RAG 是检索外部知识的方法。

RAG 检索到的结果可以写入 State，也可以被压缩后放进 Context。

---

## Q6：为什么 Agent 不能只靠聊天历史？

因为聊天历史通常：

- 冗长
- 不结构化
- 有大量无关内容
- 不适合程序路由
- 不适合断点恢复
- 不适合评估

工程 Agent 需要结构化 State 来驱动流程。

---

## Q7：在 RepoOps Assistant 中，State 如何发挥作用？

RepoOps Assistant 的 State 可以记录：

- 项目文件扫描结果
- Issue Triage 结果
- 工具执行结果
- 错误诊断结果
- 风险等级
- 下一步动作

后续 LangGraph 可以根据 State 中的字段进行条件路由。

---

## Q8：在 AUV / Fluent Agent 中，State 如何发挥作用？

AUV / Fluent Agent 的 State 可以记录：

- 当前仿真阶段
- SolidWorks 文件是否存在
- SpaceClaim 外流域是否存在
- mesh 文件是否存在
- solver 结果是否存在
- 最近 Fluent 日志
- 是否需要人工确认

这样 Agent 可以判断下一步应该运行 meshing、solver、结果校验还是错误诊断。