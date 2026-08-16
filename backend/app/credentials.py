from __future__ import annotations

import uuid

import anthropic
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.datastore.models import Credential, CredentialType

_fernet = Fernet(settings.credential_encryption_key.encode())


class CredentialResolutionError(Exception):
    """Raised when a credential_id can't be resolved to a usable secret —
    not found, belongs to a different workspace, or no fallback exists."""


def encrypt_secret(plaintext: str) -> bytes:
    return _fernet.encrypt(plaintext.encode())


def decrypt_secret(ciphertext: bytes) -> str:
    return _fernet.decrypt(ciphertext).decode()


async def create_credential(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    type_: CredentialType,
    plaintext_value: str,
    created_by: uuid.UUID,
) -> Credential:
    """Accepts a plaintext secret once. Nothing that calls this should ever
    hold onto `plaintext_value` afterward — only `credential.id` should be
    referenced by node configs from here on."""
    credential = Credential(
        workspace_id=workspace_id,
        name=name,
        type=type_,
        encrypted_value=encrypt_secret(plaintext_value),
        created_by=created_by,
    )
    db.add(credential)
    await db.commit()
    await db.refresh(credential)
    return credential


async def list_credentials(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[Credential]:
    result = await db.execute(select(Credential).where(Credential.workspace_id == workspace_id))
    return list(result.scalars().all())


async def resolve_anthropic_client(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    credential_id: uuid.UUID | None,
) -> anthropic.Anthropic:
    """The single place that turns a credential_id (or the absence of one)
    into a real Anthropic client. Node code and API routes call this —
    nothing else in the app touches `settings.anthropic_api_key` or a
    credential's `encrypted_value` directly, so swapping this for a real
    secrets manager later is a one-function change.
    """
    if credential_id is not None:
        credential = await db.get(Credential, credential_id)
        if credential is None or credential.workspace_id != workspace_id:
            raise CredentialResolutionError(
                f"Credential '{credential_id}' not found in workspace '{workspace_id}'"
            )
        if credential.type != CredentialType.ANTHROPIC_API_KEY:
            raise CredentialResolutionError(
                f"Credential '{credential_id}' is a '{credential.type.value}' credential, "
                "not an anthropic_api_key credential"
            )
        return anthropic.Anthropic(api_key=decrypt_secret(credential.encrypted_value))

    # Phase 1 fallback: no workspace credential yet, use the system-wide
    # key. Real per-workspace-default resolution is a Phase 4+ concern.
    if settings.anthropic_api_key:
        return anthropic.Anthropic(api_key=settings.anthropic_api_key)

    raise CredentialResolutionError(
        "No credential_id provided and no system-wide ANTHROPIC_API_KEY configured"
    )
