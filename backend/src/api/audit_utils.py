"""Helpers for writing audit events from API handlers."""

from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.audit_service import AuditService


async def log_audit_event(
    db: AsyncSession,
    request: Request,
    action: str,
    entity_type: str,
    entity_id: UUID | None = None,
    user_id: UUID | None = None,
    user_email: str | None = None,
    changes: dict[str, Any] | None = None,
) -> None:
    service = AuditService(db)
    client_host = request.client.host if request.client else None
    await service.log_event(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        user_email=user_email,
        changes=changes,
        ip_address=client_host,
        user_agent=request.headers.get("user-agent"),
    )
