from app.engine.context import ExecutionContext
from app.nodes.triggers.manual import ManualTriggerConfig, ManualTriggerNode


def test_manual_trigger_passes_through_the_trigger_payload():
    node = ManualTriggerNode(ManualTriggerConfig())
    context = ExecutionContext(workspace_id="w1", trigger_payload={"foo": "bar"})

    # The executor hands a root node (no incoming edges) the trigger
    # payload as `inputs` — this node's whole job is to pass it through.
    output = node.execute({"foo": "bar"}, context)

    assert output == {"foo": "bar"}
