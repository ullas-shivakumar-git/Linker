from __future__ import annotations

from pydantic import BaseModel

from app.engine.templating import render_template
from app.nodes.base import BaseNode, NodeConfig
from app.nodes.registry import register_node


class MappingEntry(BaseModel):
    output_key: str
    value_template: str


class SetTransformConfig(NodeConfig):
    mappings: list[MappingEntry] = []


@register_node
class SetTransformNode(BaseNode):
    node_type = "set_transform"
    category = "logic"
    display_name = "Set / Transform"
    description = "Reshapes data between nodes by mapping output keys to templated values."
    config_model = SetTransformConfig

    def execute(self, inputs: dict, context) -> dict:
        return {
            mapping.output_key: render_template(mapping.value_template, context)
            for mapping in self.config.mappings
        }
