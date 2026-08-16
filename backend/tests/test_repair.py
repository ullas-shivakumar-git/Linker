import json

from app.engine.executor import run_workflow
from app.engine.repair import attempt_ai_repair
from app.nodes.base import BaseNode, NodeConfig
from app.nodes.registry import register_node


class _RepairableConfig(NodeConfig):
    url: str


@register_node
class _TestRepairableNode(BaseNode):
    node_type = "test_repair_repairable"
    category = "action"
    display_name = "Test Repairable"
    description = "test-only node: fails if url doesn't start with https://"
    config_model = _RepairableConfig
    is_ai_repairable = True

    def execute(self, inputs, context):
        if not self.config.url.startswith("https://"):
            raise ValueError(f"bad url: {self.config.url}")
        return {"called": self.config.url}


class _FakeTextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeResponse:
    stop_reason = "end_turn"

    def __init__(self, text):
        self.content = [_FakeTextBlock(text)]


class _FakeMessages:
    def __init__(self, response_text):
        self._response_text = response_text

    def create(self, **kwargs):
        return _FakeResponse(self._response_text)


class _FakeAnthropicClient:
    def __init__(self, response_text):
        self.messages = _FakeMessages(response_text)


def test_attempt_ai_repair_returns_valid_correction():
    node = _TestRepairableNode(_RepairableConfig(url="example.com"))
    client = _FakeAnthropicClient(json.dumps({"url": "https://example.com"}))

    repaired = attempt_ai_repair(node, {"url": "example.com"}, "bad url: example.com", client)

    assert repaired == {"url": "https://example.com"}


def test_attempt_ai_repair_returns_none_on_invalid_schema():
    node = _TestRepairableNode(_RepairableConfig(url="example.com"))
    # Claude's proposal has the wrong type for `url` — must fail schema validation.
    client = _FakeAnthropicClient(json.dumps({"url": 12345}))

    repaired = attempt_ai_repair(node, {"url": "example.com"}, "bad url", client)

    assert repaired is None


def test_attempt_ai_repair_returns_none_on_refusal():
    node = _TestRepairableNode(_RepairableConfig(url="example.com"))
    client = _FakeAnthropicClient("")
    client.messages._response_text = ""

    class _RefusalResponse(_FakeResponse):
        stop_reason = "refusal"

    class _RefusalMessages:
        def create(self, **kwargs):
            return _RefusalResponse("")

    client.messages = _RefusalMessages()

    repaired = attempt_ai_repair(node, {"url": "example.com"}, "bad url", client)

    assert repaired is None


def test_executor_repairs_and_succeeds_end_to_end():
    nodes = [{"id": "r", "type": "test_repair_repairable", "config": {"url": "example.com"}}]
    client = _FakeAnthropicClient(json.dumps({"url": "https://example.com"}))

    result = run_workflow(nodes, [], trigger_payload={}, workspace_id="w1", anthropic_client=client)

    assert result.status == "succeeded"
    step = result.steps[0]
    assert step.ai_repair_attempted is True
    assert step.ai_repair_input == {"url": "https://example.com"}
    assert step.output["called"] == "https://example.com"


def test_executor_gives_up_cleanly_when_repair_proposal_is_invalid():
    nodes = [{"id": "r2", "type": "test_repair_repairable", "config": {"url": "still-bad"}}]
    client = _FakeAnthropicClient(json.dumps({"url": 12345}))

    result = run_workflow(nodes, [], trigger_payload={}, workspace_id="w1", anthropic_client=client)

    assert result.status == "failed"
    assert result.steps[0].ai_repair_attempted is False
