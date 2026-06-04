# Day 03 面试笔记：结构化输出与 Pydantic

## Q1：为什么 LLM Agent 需要结构化输出？

因为 Agent 的输出通常要进入后续程序流程，例如状态更新、工具选择、条件路由、风险判断和评估脚本。

自然语言输出不稳定，程序难以可靠解析。
结构化输出可以让模型判断变成可执行、可校验的数据。

---

## Q2：为什么 JSON 输出后还需要 Pydantic 校验？

因为模型可能输出格式错误或字段不合法，例如：

- 缺少字段
- 字段名写错
- 类型错误
- 枚举值不在允许范围
- JSON 外夹杂说明文字
- 编造不存在的信息

Pydantic 可以检查输出是否满足 schema，是模型输出进入工程系统前的安全边界。

---

## Q3：结构化输出和 Agent State 有什么关系？

结构化输出通常会被写入 Agent State。

例如 Issue Triage 输出：

```json
{
  "issue_type": "bug",
  "priority": "high",
  "next_action": "create_fix_plan"
}