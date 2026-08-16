import pytest

from app.engine.context import ExecutionContext
from app.nodes.logic.if_branch import IfBranchConfig, IfBranchNode

_ctx = ExecutionContext(workspace_id="w1", trigger_payload={})


@pytest.mark.parametrize(
    "config_kwargs,expected",
    [
        ({"left_template": "a", "operator": "equals", "right_template": "a"}, True),
        ({"left_template": "a", "operator": "equals", "right_template": "b"}, False),
        ({"left_template": "a", "operator": "not_equals", "right_template": "b"}, True),
        ({"left_template": "hello world", "operator": "contains", "right_template": "world"}, True),
        ({"left_template": "hello world", "operator": "contains", "right_template": "xyz"}, False),
        ({"left_template": "10", "operator": "greater_than", "right_template": "5"}, True),
        ({"left_template": "3", "operator": "less_than", "right_template": "5"}, True),
        ({"left_template": "true", "operator": "is_true", "right_template": ""}, True),
        ({"left_template": "false", "operator": "is_false", "right_template": ""}, True),
    ],
)
def test_if_branch_operators(config_kwargs, expected):
    node = IfBranchNode(IfBranchConfig(**config_kwargs))
    output = node.execute({}, _ctx)
    assert output["result"] == expected
    assert output["_next"] == ("true" if expected else "false")


def test_if_branch_renders_templates_from_context():
    ctx = ExecutionContext(workspace_id="w1", trigger_payload={"score": 75})
    node = IfBranchNode(
        IfBranchConfig(left_template="{{ trigger.score }}", operator="greater_than", right_template="50")
    )
    output = node.execute({}, ctx)
    assert output["result"] is True
