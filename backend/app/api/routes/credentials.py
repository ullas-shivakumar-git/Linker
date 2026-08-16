from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.credentials import create_credential, list_credentials
from app.datastore.models import CredentialType
from app.datastore.session import get_db

router = APIRouter(prefix="/workspaces/{workspace_id}/credentials", tags=["credentials"])


class CreateCredentialRequest(BaseModel):
    name: str
    type: CredentialType
    value: str  # plaintext — accepted once, never returned by any response
    # Phase 1 stand-in until JWT identifies the caller (Phase 4).
    created_by: uuid.UUID


class CredentialResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: CredentialType
    created_at: datetime


@router.post("", response_model=CredentialResponse, status_code=201)
async def create_credential_route(
    workspace_id: uuid.UUID,
    payload: CreateCredentialRequest,
    db: AsyncSession = Depends(get_db),
) -> CredentialResponse:
    credential = await create_credential(
        db,
        workspace_id=workspace_id,
        name=payload.name,
        type_=payload.type,
        plaintext_value=payload.value,
        created_by=payload.created_by,
    )
    return CredentialResponse(
        id=credential.id, name=credential.name, type=credential.type, created_at=credential.created_at
    )


@router.get("", response_model=list[CredentialResponse])
async def list_credentials_route(
    workspace_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[CredentialResponse]:
    credentials = await list_credentials(db, workspace_id=workspace_id)
    return [
        CredentialResponse(id=c.id, name=c.name, type=c.type, created_at=c.created_at) for c in credentials
    ]
