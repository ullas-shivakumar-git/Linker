import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.datastore.session import Base


class CredentialType(str, enum.Enum):
    ANTHROPIC_API_KEY = "anthropic_api_key"
    HTTP_BEARER = "http_bearer"
    HTTP_BASIC = "http_basic"
    GENERIC_SECRET = "generic_secret"


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[CredentialType] = mapped_column(SAEnum(CredentialType, name="credential_type"), nullable=False)
    # Fernet-encrypted bytes. Write-only from the API's point of view — no
    # route ever decrypts this back into a response.
    encrypted_value: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
