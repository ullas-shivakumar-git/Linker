from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.engine.context import ExecutionContext


class NodeConfig(BaseModel):
    """Every node type's config shape subclasses this."""


class BaseNode:
    node_type: ClassVar[str]
    category: ClassVar[str]  # "trigger" | "ai" | "action" | "logic"
    display_name: ClassVar[str]
    description: ClassVar[str]
    config_model: ClassVar[type[NodeConfig]]

    # Opt-in flags the executor's retry/AI-repair wrapper checks — most
    # node types leave both False (a bad set_transform input shouldn't be
    # blindly retried, for instance).
    is_retryable: ClassVar[bool] = False
    is_ai_repairable: ClassVar[bool] = False

    def __init__(self, config: NodeConfig):
        self.config = config

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        raise NotImplementedError
