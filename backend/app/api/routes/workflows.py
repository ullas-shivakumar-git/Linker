from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

import app.nodes  # noqa: F401 — import for side effect: registers all built-in node types
from app.credentials import CredentialResolutionError, resolve_anthropic_client
from app.datastore.models import (
    Execution,
    ExecutionStatus,
    ExecutionStep,
    StepStatus,
    TriggerType,
    Workflow,
    WorkflowVersion,
)
from app.datastore.session import get_db
from app.engine.executor import WorkflowCycleError, run_workflow, topological_sort

router = APIRouter(prefix="/workspaces/{workspace_id}/workflows", tags=["workflows"])


class GraphPayload(BaseModel):
    nodes: list[dict]
    edges: list[dict]


class CreateWorkflowRequest(BaseModel):
    name: str
    description: Optional[str] = None
    graph: GraphPayload
    created_by: uuid.UUID  # Phase 1 stand-in until JWT identifies the caller


class UpdateWorkflowRequest(BaseModel):
    graph: GraphPayload
    created_by: uuid.UUID


class WorkflowResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: Optional[str]
    is_active: bool
    current_version_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime


class WorkflowDetailResponse(WorkflowResponse):
    graph: Optional[GraphPayload]
    version_number: Optional[int]


class ExecuteWorkflowRequest(BaseModel):
    trigger_payload: dict = {}
    credential_id: Optional[uuid.UUID] = None


class ExecutionStepResponse(BaseModel):
    node_id: str
    node_type: str
    status: str
    input: Optional[dict]
    output: Optional[dict]
    error: Optional[str]
    retry_count: int
    ai_repair_attempted: bool
    ai_repair_input: Optional[dict]


class ExecutionResponse(BaseModel):
    id: uuid.UUID
    status: str
    error: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    steps: list[ExecutionStepResponse]


def _validate_graph(graph: GraphPayload) -> None:
    """Rejects a cyclic graph at save time, before anyone tries to run it."""
    try:
        topological_sort(graph.nodes, graph.edges)
    except WorkflowCycleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


async def _get_workflow_or_404(db: AsyncSession, workspace_id: uuid.UUID, workflow_id: uuid.UUID) -> Workflow:
    workflow = await db.get(Workflow, workflow_id)
    if workflow is None or workflow.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.post("", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    workspace_id: uuid.UUID, payload: CreateWorkflowRequest, db: AsyncSession = Depends(get_db)
) -> Workflow:
    _validate_graph(payload.graph)

    workflow = Workflow(workspace_id=workspace_id, name=payload.name, description=payload.description)
    db.add(workflow)
    await db.flush()

    version = WorkflowVersion(
        workflow_id=workflow.id,
        version_number=1,
        graph_json=payload.graph.model_dump(),
        created_by=payload.created_by,
    )
    db.add(version)
    await db.flush()

    workflow.current_version_id = version.id
    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(workspace_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[Workflow]:
    from sqlalchemy import select

    result = await db.execute(select(Workflow).where(Workflow.workspace_id == workspace_id))
    return list(result.scalars().all())


@router.get("/{workflow_id}", response_model=WorkflowDetailResponse)
async def get_workflow(
    workspace_id: uuid.UUID, workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> WorkflowDetailResponse:
    workflow = await _get_workflow_or_404(db, workspace_id, workflow_id)

    graph = None
    version_number = None
    if workflow.current_version_id is not None:
        version = await db.get(WorkflowVersion, workflow.current_version_id)
        if version is not None:
            graph = GraphPayload(**version.graph_json)
            version_number = version.version_number

    return WorkflowDetailResponse(
        id=workflow.id,
        workspace_id=workflow.workspace_id,
        name=workflow.name,
        description=workflow.description,
        is_active=workflow.is_active,
        current_version_id=workflow.current_version_id,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        graph=graph,
        version_number=version_number,
    )


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workspace_id: uuid.UUID,
    workflow_id: uuid.UUID,
    payload: UpdateWorkflowRequest,
    db: AsyncSession = Depends(get_db),
) -> Workflow:
    """Saves a NEW immutable version rather than editing one in place — see
    PLAN.md §4 on why (rollback, and in-flight executions keep running
    against the version they started with)."""
    _validate_graph(payload.graph)
    workflow = await _get_workflow_or_404(db, workspace_id, workflow_id)

    from sqlalchemy import func, select

    latest_version_number = await db.scalar(
        select(func.max(WorkflowVersion.version_number)).where(WorkflowVersion.workflow_id == workflow.id)
    )

    version = WorkflowVersion(
        workflow_id=workflow.id,
        version_number=(latest_version_number or 0) + 1,
        graph_json=payload.graph.model_dump(),
        created_by=payload.created_by,
    )
    db.add(version)
    await db.flush()

    workflow.current_version_id = version.id
    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.post("/{workflow_id}/execute", response_model=ExecutionResponse)
async def execute_workflow(
    workspace_id: uuid.UUID,
    workflow_id: uuid.UUID,
    payload: ExecuteWorkflowRequest,
    db: AsyncSession = Depends(get_db),
) -> ExecutionResponse:
    workflow = await _get_workflow_or_404(db, workspace_id, workflow_id)
    if workflow.current_version_id is None:
        raise HTTPException(status_code=400, detail="Workflow has no saved version yet")

    version = await db.get(WorkflowVersion, workflow.current_version_id)
    assert version is not None  # current_version_id always points at a real row

    try:
        anthropic_client = await resolve_anthropic_client(
            db, workspace_id=workspace_id, credential_id=payload.credential_id
        )
    except CredentialResolutionError:
        # Don't fail the whole run just because no credential is configured
        # — only AI nodes need it, and they raise their own clear error
        # (NodeExecutionError) if they actually get called without one.
        anthropic_client = None

    execution = Execution(
        workflow_id=workflow.id,
        workflow_version_id=version.id,
        trigger_type=TriggerType.MANUAL,
        status=ExecutionStatus.RUNNING,
        input_payload=payload.trigger_payload,
        started_at=datetime.now(timezone.utc),
    )
    db.add(execution)
    await db.flush()

    result = run_workflow(
        nodes=version.graph_json["nodes"],
        edges=version.graph_json["edges"],
        trigger_payload=payload.trigger_payload,
        workspace_id=str(workspace_id),
        anthropic_client=anthropic_client,
    )

    execution.status = ExecutionStatus.SUCCEEDED if result.status == "succeeded" else ExecutionStatus.FAILED
    execution.error = result.error
    execution.finished_at = datetime.now(timezone.utc)

    step_responses: list[ExecutionStepResponse] = []
    for step in result.steps:
        db.add(
            ExecutionStep(
                execution_id=execution.id,
                node_id=step.node_id,
                node_type=step.node_type,
                status=StepStatus(step.status),
                input_json=step.input,
                output_json=step.output,
                error=step.error,
                retry_count=step.retry_count,
                ai_repair_attempted=step.ai_repair_attempted,
                ai_repair_input=step.ai_repair_input,
            )
        )
        step_responses.append(
            ExecutionStepResponse(
                node_id=step.node_id,
                node_type=step.node_type,
                status=step.status,
                input=step.input,
                output=step.output,
                error=step.error,
                retry_count=step.retry_count,
                ai_repair_attempted=step.ai_repair_attempted,
                ai_repair_input=step.ai_repair_input,
            )
        )

    await db.commit()

    return ExecutionResponse(
        id=execution.id,
        status=execution.status.value,
        error=execution.error,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        steps=step_responses,
    )
