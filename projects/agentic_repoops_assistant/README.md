# Agentic RepoOps Assistant

## 1. 项目定位

Agentic RepoOps Assistant 是一个面向代码仓库、项目文档、日志和 Issue 的工程 Agent。

它的目标不是简单聊天，而是帮助开发者完成项目运维类任务：

- 分析项目结构
- 判断项目当前状态
- 分类 GitHub Issue
- 检索 README / docs / logs
- 诊断错误日志
- 生成修复计划
- 判断是否需要人工确认
- 记录 Agent 执行轨迹
- 评估 Agent 输出是否可靠

## 2. 为什么这个项目适合作为 Agent 项目？

因为代码仓库和项目运维任务天然具有 Agent 特征：

- 有明确目标：修复问题、理解项目、推进任务
- 有状态：文件、日志、Issue、依赖、测试结果
- 有工具：读文件、查日志、搜索文本、运行测试
- 有反馈：工具返回结果、错误信息、测试是否通过
- 有风险：修改文件、运行命令、删除文件需要权限控制
- 可评估：分类是否正确、修复建议是否有效、是否触发人工确认

## 3. 本月逐步实现目标

### v0：结构化输出

- Issue Triage
- Pydantic 校验
- 结构化 JSON 输出

### v1：工具调用

- 扫描项目文件
- 读取 README
- 读取日志
- 搜索关键词

### v2：RAG

- 检索项目文档
- 检索错误知识库
- 返回带依据的建议

### v3：Agent Loop

- ReAct 风格循环
- 根据观察结果决定下一步动作

### v4：LangGraph Workflow

- 状态图
- 条件路由
- human-in-the-loop

### v5：Evaluation + Guardrails

- 测试集
- 评估脚本
- 权限控制
- Trace 日志

## 4. 与 AUV Fluent Simulation Agent 的关系

Agentic RepoOps Assistant 是通用主线项目，用来训练标准 Agent 工程能力。

后续这些能力会迁移到 AUV Fluent Simulation Agent：

- 文件检查
- 日志诊断
- 阶段判断
- 错误恢复
- RAG 知识库
- 状态机
- 评估指标
- 人工确认机制