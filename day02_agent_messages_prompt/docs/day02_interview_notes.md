# Day 02 面试问题整理

## Q1：LLM 和 Agent 有什么区别？

LLM 是语言理解和生成模型，主要完成文本输入到文本输出。
Agent 是一个能够围绕目标执行多步骤任务的系统，通常包括 LLM、状态管理、工具调用、反馈机制和评估模块。

## Q2：Agent 和普通自动化脚本、workflow 有什么区别？

普通脚本通常按照固定流程执行。
Agent 能根据当前状态判断下一步，调用不同工具，读取反馈，处理异常，并在高风险步骤请求人工确认。
Workflow：有结构的流程编排，Workflow 比普通脚本更像“流程图”。

普通脚本：你告诉它每一步怎么做
Workflow：你设计好流程，它按规则流转
LLM：你问它，它给你答案
Agent：你给它目标，它自己拆步骤并执行

## Q3：system prompt 和 user prompt 有什么区别？

system prompt 用于设置长期规则、角色、边界和输出约束。
user prompt 表示当前具体任务。

## Q4：为什么多轮对话 API 需要传历史 messages？

很多 LLM API 本身是无状态的。
如果不传历史，模型无法知道前文发生了什么。
Agent 系统需要显式维护上下文和状态。

## Q5：为什么 Prompt Engineering 不等于 Agent Engineering？

Prompt Engineering 主要关注如何组织模型输入。
Agent Engineering 还包括状态管理、工具调用、错误处理、工作流编排、评估、安全和部署。