from dataclasses import dataclass, field


@dataclass
class ExecutionContext:
    """Shared state for one workflow run, passed to every node's execute()."""

    workspace_id: str
    trigger_payload: dict
    node_outputs: dict[str, dict] = field(default_factory=dict)
