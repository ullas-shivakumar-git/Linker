from app.nodes.base import BaseNode, NodeConfig
from app.nodes.registry import register_node


class ManualTriggerConfig(NodeConfig):
    pass


@register_node
class ManualTriggerNode(BaseNode):
    node_type = "manual_trigger"
    category = "trigger"
    display_name = "Manual Trigger"
    description = "Starts the workflow when run manually via the API, with whatever input payload was provided."
    config_model = ManualTriggerConfig

    def execute(self, inputs: dict, context) -> dict:
        # This node has no incoming edges, so the executor hands it
        # context.trigger_payload as `inputs` — pass it through as-is so
        # downstream nodes can read it via {{ nodes.<this_id>.field }}.
        return inputs
