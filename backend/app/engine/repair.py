from __future__ import annotations

import json
from typing import TYPE_CHECKING

import anthropic
from pydantic import ValidationError

if TYPE_CHECKING:
    from app.nodes.base import BaseNode

REPAIR_MODEL = "claude-opus-5"


def attempt_ai_repair(
    node: "BaseNode",
    failed_config: dict,
    error: str,
    client: anthropic.Anthropic,
) -> dict | None:
    """On a node's last failed attempt, ask Claude to propose a corrected
    config — constrained via structured output to the node's own Pydantic
    schema, so a bad proposal is rejected automatically rather than
    silently accepted. Returns the corrected config dict, or None if
    Claude couldn't produce something that validates (the executor treats
    None as "repair didn't work, fail normally").
    """
    schema = node.config_model.model_json_schema()

    response = client.messages.create(
        model=REPAIR_MODEL,
        max_tokens=2048,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[
            {
                "role": "user",
                "content": (
                    "A workflow automation node failed. Given its config schema, "
                    "the config that was used, and the error it raised, propose a "
                    "corrected config that fixes the problem while preserving the "
                    "original intent as closely as possible. Respond with only the "
                    "corrected config, matching the schema exactly.\n\n"
                    f"Node type: {node.node_type}\n"
                    f"Config schema: {json.dumps(schema)}\n"
                    f"Failed config: {json.dumps(failed_config)}\n"
                    f"Error: {error}"
                ),
            }
        ],
    )

    if response.stop_reason == "refusal":
        return None

    text = next((block.text for block in response.content if block.type == "text"), None)
    if text is None:
        return None

    try:
        candidate = json.loads(text)
    except json.JSONDecodeError:
        return None

    try:
        node.config_model.model_validate(candidate)
    except ValidationError:
        return None

    return candidate
