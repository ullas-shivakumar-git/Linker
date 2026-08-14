from __future__ import annotations

from dataclasses import dataclass, field

import anthropic


@dataclass
class ExecutionContext:
    """Shared state for one workflow run, passed to every node's execute()."""

    workspace_id: str
    trigger_payload: dict
    node_outputs: dict[str, dict] = field(default_factory=dict)
    # Same client the executor's AI-repair mechanism uses — nodes that need
    # to call Claude directly (claude_ai) read it from here rather than
    # each resolving their own, keeping credential resolution in one place.
    anthropic_client: anthropic.Anthropic | None = None
