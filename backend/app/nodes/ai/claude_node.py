from __future__ import annotations

import json
from typing import Literal, Optional

from app.engine.templating import render_template
from app.nodes.base import BaseNode, NodeConfig
from app.nodes.registry import register_node


class ClaudeNodeConfig(NodeConfig):
    model: Literal["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"] = "claude-opus-5"
    system_prompt_template: str = ""
    user_prompt_template: str
    max_tokens: int = 4096
    structured_output: bool = False
    json_schema: Optional[dict] = None
    # Falls back to a workspace default / ANTHROPIC_API_KEY until the
    # credentials vault (Milestone 1.5) exists.
    credential_id: Optional[str] = None


class NodeExecutionError(Exception):
    """A node failed in a way the executor should treat as a normal failed
    step (eligible for retry/AI-repair) rather than a bug in our code."""


@register_node
class ClaudeAINode(BaseNode):
    node_type = "claude_ai"
    category = "ai"
    display_name = "Claude"
    description = "Calls Claude with a prompt built from upstream node outputs."
    config_model = ClaudeNodeConfig
    is_retryable = True

    def execute(self, inputs: dict, context) -> dict:
        if context.anthropic_client is None:
            raise NodeExecutionError(
                "No Anthropic client available — a workspace credential (or "
                "ANTHROPIC_API_KEY) is required to run a claude_ai node."
            )

        user_message = render_template(self.config.user_prompt_template, context)

        request_kwargs: dict = {}
        if self.config.system_prompt_template:
            request_kwargs["system"] = render_template(self.config.system_prompt_template, context)
        if self.config.structured_output:
            request_kwargs["output_config"] = {
                "format": {"type": "json_schema", "schema": self.config.json_schema}
            }

        response = context.anthropic_client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            messages=[{"role": "user", "content": user_message}],
            **request_kwargs,
        )

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise NodeExecutionError(f"Claude declined the request (category={category})")

        text = next((block.text for block in response.content if block.type == "text"), "")
        result = {"text": text, "model": response.model}

        if self.config.structured_output:
            result["json"] = json.loads(text)

        return result
