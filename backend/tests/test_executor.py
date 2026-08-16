from app.engine.executor import WorkflowCycleError, run_workflow, topological_sort
from app.nodes.base import BaseNode, NodeConfig
from app.nodes.registry import register_node


class _PassthroughConfig(NodeConfig):
    label: str = ""


@register_node
class _TestPassthroughNode(BaseNode):
    node_type = "test_executor_passthrough"
    category = "logic"
    display_name = "Test Passthrough"
    description = "test-only node: echoes its input plus a label"
    config_model = _PassthroughConfig

    def execute(self, inputs, context):
        return {"label": self.config.label, "saw": inputs}


class _FlakyConfig(NodeConfig):
    pass


_flaky_attempts = {"n": 0}


@register_node
class _TestFlakyNode(BaseNode):
    node_type = "test_executor_flaky"
    category = "action"
    display_name = "Test Flaky"
    description = "test-only node: fails twice then succeeds"
    config_model = _FlakyConfig
    is_retryable = True

    def execute(self, inputs, context):
        _flaky_attempts["n"] += 1
        if _flaky_attempts["n"] < 3:
            raise RuntimeError(f"transient failure #{_flaky_attempts['n']}")
        return {"ok": True}


class _BranchConfig(NodeConfig):
    pass


@register_node
class _TestBranchNode(BaseNode):
    node_type = "test_executor_branch"
    category = "logic"
    display_name = "Test Branch"
    description = "test-only node: always takes the true path"
    config_model = _BranchConfig

    def execute(self, inputs, context):
        return {"_next": "true"}


def test_linear_chain():
    nodes = [
        {"id": "a", "type": "test_executor_passthrough", "config": {"label": "A"}},
        {"id": "b", "type": "test_executor_passthrough", "config": {"label": "B"}},
        {"id": "c", "type": "test_executor_passthrough", "config": {"label": "C"}},
    ]
    edges = [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]

    result = run_workflow(nodes, edges, trigger_payload={"x": 1}, workspace_id="w1")

    assert result.status == "succeeded"
    assert [s.node_id for s in result.steps] == ["a", "b", "c"]
    assert result.steps[2].output["saw"]["label"] == "B"  # c saw b's output


def test_diamond_merge_point():
    nodes = [
        {"id": "a", "type": "test_executor_passthrough", "config": {"label": "A"}},
        {"id": "b", "type": "test_executor_passthrough", "config": {"label": "B"}},
        {"id": "c", "type": "test_executor_passthrough", "config": {"label": "C"}},
        {"id": "d", "type": "test_executor_passthrough", "config": {"label": "D"}},
    ]
    edges = [
        {"source": "a", "target": "b"},
        {"source": "a", "target": "c"},
        {"source": "b", "target": "d"},
        {"source": "c", "target": "d"},
    ]

    result = run_workflow(nodes, edges, trigger_payload={}, workspace_id="w1")

    assert result.status == "succeeded"
    d_step = next(s for s in result.steps if s.node_id == "d")
    assert set(d_step.input.keys()) == {"b", "c"}


def test_cycle_is_rejected():
    nodes = [{"id": "a"}, {"id": "b"}]
    edges = [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]

    try:
        topological_sort(nodes, edges)
        assert False, "expected WorkflowCycleError"
    except WorkflowCycleError:
        pass


def test_retry_then_succeed():
    _flaky_attempts["n"] = 0
    nodes = [{"id": "f", "type": "test_executor_flaky", "config": {}}]

    result = run_workflow(nodes, [], trigger_payload={}, workspace_id="w1", retry_backoff_seconds=0.01)

    assert result.status == "succeeded"
    assert result.steps[0].retry_count == 2


def test_branch_skip_propagation():
    nodes = [
        {"id": "start", "type": "test_executor_branch", "config": {}},
        {"id": "true_path", "type": "test_executor_passthrough", "config": {"label": "T"}},
        {"id": "false_path", "type": "test_executor_passthrough", "config": {"label": "F"}},
    ]
    edges = [
        {"source": "start", "target": "true_path", "condition": "true"},
        {"source": "start", "target": "false_path", "condition": "false"},
    ]

    result = run_workflow(nodes, edges, trigger_payload={}, workspace_id="w1")

    assert result.status == "succeeded"
    statuses = {s.node_id: s.status for s in result.steps}
    assert statuses["true_path"] == "succeeded"
    assert statuses["false_path"] == "skipped"
