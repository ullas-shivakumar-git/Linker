from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.datastore.models import User, Workspace, WorkspaceMembership, WorkspaceRole
from app.datastore.session import get_db

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    owner_email: str
    workspace_name: str


class WorkspaceResponse(BaseModel):
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    name: str


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(payload: CreateWorkspaceRequest, db: AsyncSession = Depends(get_db)) -> WorkspaceResponse:
    """Phase 1 stand-in for real signup — no password hashing or JWT yet
    (that's Phase 4). Creates a user, a workspace, and an owner membership
    in one call so there's something real to point workflows/credentials
    at before auth exists.
    """
    user = User(email=payload.owner_email, hashed_password="unset")
    db.add(user)
    await db.flush()

    workspace = Workspace(name=payload.workspace_name, owner_user_id=user.id)
    db.add(workspace)
    await db.flush()

    db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER))
    await db.commit()

    return WorkspaceResponse(workspace_id=workspace.id, user_id=user.id, name=workspace.name)
