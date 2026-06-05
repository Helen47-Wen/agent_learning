# Day 04：Tool Calling

## 今日目标

学习 Tool Calling 的基本原理，并为 Agentic RepoOps Assistant 实现第一版只读工具层。

## 核心文件

- `schemas/tool_result_schema.py`：统一工具返回结构
- `schemas/tool_call_schema.py`：模型选择工具的结构化决策
- `tools/file_tools.py`：只读文件工具
- `examples/01_repo_file_scanner.py`：直接测试工具
- `examples/02_tool_call_router.py`：LLM 选择工具，Python 执行工具

## 运行方式

```powershell
cd C:\Users\lijic\Desktop\agent_learning\day04_tool_calling
python examples\01_repo_file_scanner.py
python examples\02_tool_call_router.py