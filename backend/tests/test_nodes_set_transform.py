from app.engine.context import ExecutionContext
from app.nodes.logic.set_transform import MappingEntry, SetTransformConfig, SetTransformNode


def test_set_transform_maps_output_keys_with_templating():
    ctx = ExecutionContext(
        workspace_id="w1",
        trigger_payload={"name": "Ullas"},
        node_outputs={"prev": {"score": 75}},
    )
    node = SetTransformNode(
        SetTransformConfig(
            mappings=[
                MappingEntry(output_key="greeting", value_template="hello {{ trigger.name }}"),
                MappingEntry(output_key="prev_score", value_template="{{ nodes.prev.score }}"),
            ]
        )
    )

    output = node.execute({}, ctx)

    assert output == {"greeting": "hello Ullas", "prev_score": "75"}


def test_set_transform_with_no_mappings_returns_empty_dict():
    ctx = ExecutionContext(workspace_id="w1", trigger_payload={})
    node = SetTransformNode(SetTransformConfig())

    assert node.execute({}, ctx) == {}
