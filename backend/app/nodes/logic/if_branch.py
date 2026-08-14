from __future__ import annotations

from typing import Literal

from app.engine.templating import render_template
from app.nodes.base import BaseNode, NodeConfig
from app.nodes.registry import register_node

Operator = Literal["equals", "not_equals", "contains", "greater_than", "less_than", "is_true", "is_false"]


class IfBranchConfig(NodeConfig):
    left_template: str
    operator: Operator = "equals"
    right_template: str = ""


def _try_number(value: str):
    try:
        return float(value)
    except ValueError:
        return value


@register_node
class IfBranchNode(BaseNode):
    node_type = "if_branch"
    category = "logic"
    display_name = "If / Else"
    description = (
        "Evaluates a condition and routes execution down the true or false "
        "branch. Downstream nodes on the branch not taken are marked skipped."
    )
    config_model = IfBranchConfig

    def execute(self, inputs: dict, context) -> dict:
        left = render_template(self.config.left_template, context)
        right = render_template(self.config.right_template, context) if self.config.right_template else ""

        op = self.config.operator
        if op == "equals":
            result = left == right
        elif op == "not_equals":
            result = left != right
        elif op == "contains":
            result = right in left
        elif op == "greater_than":
            result = _try_number(left) > _try_number(right)
        elif op == "less_than":
            result = _try_number(left) < _try_number(right)
        elif op == "is_true":
            result = left.strip().lower() in ("true", "1", "yes")
        elif op == "is_false":
            result = left.strip().lower() in ("false", "0", "no")
        else:
            raise ValueError(f"Unknown operator: {op}")

        # Edges carry a matching `condition: "true" | "false"` field — the
        # executor only descends into edges whose condition matches _next.
        return {"result": result, "_next": "true" if result else "false"}
