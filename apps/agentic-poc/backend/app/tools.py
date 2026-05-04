from __future__ import annotations

import ast
import operator as op
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    ok: bool
    output: dict[str, Any]
    error: str | None = None


KNOWLEDGE_BASE = {
    "refund_policy": "Refunds above $100 require manager approval.",
    "support_hours": "Support hours are Monday-Friday, 9am-5pm local time.",
}


TASK_STATE: dict[str, str] = {}


def _safe_eval(expr: str) -> float:
    operators = {
        ast.Add: op.add,
        ast.Sub: op.sub,
        ast.Mult: op.mul,
        ast.Div: op.truediv,
        ast.USub: op.neg,
    }

    def eval_node(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return operators[type(node.op)](eval_node(node.left), eval_node(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in operators:
            return operators[type(node.op)](eval_node(node.operand))
        raise ValueError("unsafe expression")

    parsed = ast.parse(expr, mode="eval")
    return eval_node(parsed.body)


def execute_tool(name: str, arguments: dict[str, Any]) -> ToolResult:
    if name == "knowledge_lookup":
        topic = str(arguments.get("topic", "")).strip()
        if not topic:
            return ToolResult(ok=False, output={}, error="topic is required")
        snippet = KNOWLEDGE_BASE.get(topic)
        if not snippet:
            return ToolResult(ok=False, output={}, error=f"no knowledge found for topic `{topic}`")
        return ToolResult(ok=True, output={"topic": topic, "snippet": snippet})

    if name == "calculator":
        expression = str(arguments.get("expression", "")).strip()
        if not expression:
            return ToolResult(ok=False, output={}, error="expression is required")
        try:
            value = _safe_eval(expression)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, output={}, error=f"invalid expression: {exc}")
        return ToolResult(ok=True, output={"expression": expression, "result": value})

    if name == "task_state_update":
        task_id = str(arguments.get("task_id", "")).strip()
        state = str(arguments.get("state", "")).strip()
        if not task_id or not state:
            return ToolResult(ok=False, output={}, error="task_id and state are required")
        TASK_STATE[task_id] = state
        return ToolResult(ok=True, output={"task_id": task_id, "state": state})

    return ToolResult(ok=False, output={}, error=f"unknown tool `{name}`")
