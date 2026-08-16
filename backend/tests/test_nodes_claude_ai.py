import json

import pytest

from app.engine.context import ExecutionContext
from app.nodes.ai.claude_node import ClaudeAINode, ClaudeNodeConfig, NodeExecutionError


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, text, stop_reason="end_turn", model="claude-opus-5"):
        self.content = [_Block(text)]
        self.stop_reason = stop_reason
        self.model = model
        self.stop_details = None


class _Messages:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._response


class _Client:
    def __init__(self, response):
        self.messages = _Messages(response)


def test_claude_ai_renders_prompt_template_and_returns_text():
    client = _Client(_Response("The answer is 42."))
    ctx = ExecutionContext(
        workspace_id="w1", trigger_payload={"question": "what is the answer?"}, anthropic_client=client
    )
    node = ClaudeAINode(ClaudeNodeConfig(user_prompt_template="Q: {{ trigger.question }}"))

    output = node.execute({}, ctx)

    assert output["text"] == "The answer is 42."
    assert client.messages.last_kwargs["messages"][0]["content"] == "Q: what is the answer?"
    assert "system" not in client.messages.last_kwargs  # no system_prompt_template configured


def test_claude_ai_includes_rendered_system_prompt_when_configured():
    client = _Client(_Response("ok"))
    ctx = ExecutionContext(workspace_id="w1", trigger_payload={"tone": "formal"}, anthropic_client=client)
    node = ClaudeAINode(
        ClaudeNodeConfig(
            system_prompt_template="Respond in a {{ trigger.tone }} tone.",
            user_prompt_template="hello",
        )
    )

    node.execute({}, ctx)

    assert client.messages.last_kwargs["system"] == "Respond in a formal tone."


def test_claude_ai_structured_output():
    client = _Client(_Response(json.dumps({"sentiment": "positive"})))
    ctx = ExecutionContext(workspace_id="w1", trigger_payload={}, anthropic_client=client)
    node = ClaudeAINode(
        ClaudeNodeConfig(
            user_prompt_template="classify",
            structured_output=True,
            json_schema={"type": "object", "properties": {"sentiment": {"type": "string"}}},
        )
    )

    output = node.execute({}, ctx)

    assert output["json"] == {"sentiment": "positive"}
    assert "output_config" in client.messages.last_kwargs


def test_claude_ai_raises_clean_error_on_refusal():
    client = _Client(_Response("", stop_reason="refusal"))
    ctx = ExecutionContext(workspace_id="w1", trigger_payload={}, anthropic_client=client)
    node = ClaudeAINode(ClaudeNodeConfig(user_prompt_template="x"))

    with pytest.raises(NodeExecutionError):
        node.execute({}, ctx)


def test_claude_ai_raises_clean_error_with_no_client():
    ctx = ExecutionContext(workspace_id="w1", trigger_payload={})  # anthropic_client defaults to None
    node = ClaudeAINode(ClaudeNodeConfig(user_prompt_template="x"))

    with pytest.raises(NodeExecutionError):
        node.execute({}, ctx)
