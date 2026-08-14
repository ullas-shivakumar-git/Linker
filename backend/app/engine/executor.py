from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import anthropic

from app.engine.context import ExecutionContext
from app.engine.repair import attempt_ai_repair
from app.nodes.base import BaseNode
from app.nodes.registry import get_node_class


class WorkflowCycleError(Exception):
    """Raised when a workflow graph isn't a DAG."""


@dataclass
class StepResult:
    node_id: str
    node_type: str
    status: str  # "succeeded" | "failed" | "skipped"
    input: dict | None = None
    output: dict | None = None
    error: str | None = None
    retry_count: int = 0
    ai_repair_attempted: bool = False
    ai_repair_input: dict | None = None


@dataclass
class ExecutionResult:
    status: str  # "succeeded" | "failed"
    steps: list[StepResult] = field(default_factory=list)
    error: str | None = None


def topological_sort(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Kahn's algorithm. Returns node ids ordered so every node comes after
    everything that feeds into it. Raises WorkflowCycleError if the graph
    isn't a DAG — called at save time (PUT /workflows/{id}), not run time,
    so a broken workflow is rejected before anyone tries to execute it.
    """
    node_ids = [n["id"] for n in nodes]
    in_degree = {nid: 0 for nid in node_ids}
    adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}

    for edge in edges:
        adjacency[edge["source"]].append(edge["target"])
        in_degree[edge["target"]] += 1

    queue = deque(nid for nid in node_ids if in_degree[nid] == 0)
    order: list[str] = []

    while queue:
        current = queue.popleft()
        order.append(current)
        for neighbor in adjacency[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(node_ids):
        raise WorkflowCycleError("Workflow graph contains a cycle")

    return order


def _resolve_inputs(node_id: str, incoming: list[dict], context: ExecutionContext) -> dict:
    if not incoming:
        return context.trigger_payload
    if len(incoming) == 1:
        return context.node_outputs.get(incoming[0]["source"], {})
    # Merge point: expose each upstream node's output keyed by its node_id
    # rather than arbitrarily picking one.
    return {e["source"]: context.node_outputs.get(e["source"], {}) for e in incoming}


def _is_edge_active(edge: dict, context: ExecutionContext, skipped: set[str]) -> bool:
    source = edge["source"]
    if source in skipped:
        return False
    condition = edge.get("condition")
    if condition is None:
        return True
    # if_branch (Milestone 1.4) reports which branch it took via `_next`
    # on its output; an edge with a `condition` only fires on a match.
    return context.node_outputs.get(source, {}).get("_next") == condition


def run_workflow(
    nodes: list[dict],
    edges: list[dict],
    trigger_payload: dict,
    workspace_id: str,
    anthropic_client: anthropic.Anthropic | None = None,
    max_retry_attempts: int = 3,
    retry_backoff_seconds: float = 0.5,
) -> ExecutionResult:
    """Execute a workflow graph synchronously, in-process. Returns per-node
    step data mirroring the execution_steps table — persisting it is the
    API layer's job (Milestone 1.6), not this function's, which keeps the
    engine testable with no database involved.
    """
    order = topological_sort(nodes, edges)
    node_by_id = {n["id"]: n for n in nodes}
    context = ExecutionContext(
        workspace_id=workspace_id,
        trigger_payload=trigger_payload,
        anthropic_client=anthropic_client,
    )

    steps: list[StepResult] = []
    skipped: set[str] = set()

    for node_id in order:
        node_def = node_by_id[node_id]
        node_type = node_def["type"]
        incoming = [e for e in edges if e["target"] == node_id]

        if incoming and not any(_is_edge_active(e, context, skipped) for e in incoming):
            skipped.add(node_id)
            context.node_outputs[node_id] = {}
            steps.append(StepResult(node_id=node_id, node_type=node_type, status="skipped"))
            continue

        node_class = get_node_class(node_type)
        node = node_class(node_class.config_model.model_validate(node_def.get("config", {})))
        inputs = _resolve_inputs(node_id, incoming, context)

        step = _execute_with_retry(
            node=node,
            node_id=node_id,
            node_type=node_type,
            inputs=inputs,
            context=context,
            anthropic_client=anthropic_client,
            max_retry_attempts=max_retry_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
        )
        steps.append(step)
        context.node_outputs[node_id] = step.output or {}

        if step.status == "failed":
            return ExecutionResult(status="failed", steps=steps, error=step.error)

    return ExecutionResult(status="succeeded", steps=steps)


def _execute_with_retry(
    *,
    node: BaseNode,
    node_id: str,
    node_type: str,
    inputs: dict,
    context: ExecutionContext,
    anthropic_client: anthropic.Anthropic | None,
    max_retry_attempts: int,
    retry_backoff_seconds: float,
) -> StepResult:
    attempts = max_retry_attempts if node.is_retryable else 1
    last_error: str | None = None

    for attempt in range(1, attempts + 1):
        try:
            output = node.execute(inputs, context)
            return StepResult(
                node_id=node_id,
                node_type=node_type,
                status="succeeded",
                input=inputs,
                output=output,
                retry_count=attempt - 1,
            )
        except Exception as exc:
            last_error = str(exc)
            is_last_attempt = attempt == attempts

            if is_last_attempt and node.is_ai_repairable and anthropic_client is not None:
                failed_config = node.config.model_dump(mode="json")
                repaired_config = attempt_ai_repair(node, failed_config, last_error, anthropic_client)

                if repaired_config is not None:
                    try:
                        node.config = node.config_model.model_validate(repaired_config)
                        output = node.execute(inputs, context)
                        return StepResult(
                            node_id=node_id,
                            node_type=node_type,
                            status="succeeded",
                            input=inputs,
                            output=output,
                            retry_count=attempt - 1,
                            ai_repair_attempted=True,
                            ai_repair_input=repaired_config,
                        )
                    except Exception as repair_exc:
                        return StepResult(
                            node_id=node_id,
                            node_type=node_type,
                            status="failed",
                            input=inputs,
                            error=str(repair_exc),
                            retry_count=attempt - 1,
                            ai_repair_attempted=True,
                            ai_repair_input=repaired_config,
                        )

            if is_last_attempt:
                break

            time.sleep(retry_backoff_seconds * attempt)

    return StepResult(
        node_id=node_id,
        node_type=node_type,
        status="failed",
        input=inputs,
        error=last_error,
        retry_count=attempts - 1,
    )
