"""Source CRUD operations service (T040)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.flow import Flow
from src.models.schedule import Schedule
from src.models.source import Source
from src.models.source_credential import SourceCredential
from src.services.connection import (
    decrypt_password,
    encrypt_password,
    test_connection,
    test_s3_connection,
)
from src.services.run_service import RunService


class SourceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_sources(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Source]:
        query = select(Source).where(Source.deleted_at.is_(None))
        if status:
            query = query.where(Source.connection_status == status)
        query = query.order_by(Source.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_source(self, source_id: UUID) -> Source | None:
        query = (
            select(Source)
            .options(selectinload(Source.credential))
            .where(Source.id == source_id, Source.deleted_at.is_(None))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_source(
        self,
        name: str,
        source_type: str,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        description: str | None = None,
        created_by: UUID | None = None,
        auto_commit: bool = True,
    ) -> Source:
        normalized_source_type = (source_type or "postgres").lower()
        source = Source(
            name=name,
            source_type=normalized_source_type,
            host=host,
            port=port,
            database=database,
            username=username,
            description=description,
            created_by=created_by,
            connection_status="pending",
        )
        self.session.add(source)
        await self.session.flush()

        # Encrypt and store password
        encrypted = await encrypt_password(self.session, password)
        credential = SourceCredential(
            source_id=source.id,
            password_encrypted=encrypted,
        )
        self.session.add(credential)

        # Test connection
        if normalized_source_type == "s3":
            result = await test_s3_connection(host, port, database, username, password)
        else:
            result = await test_connection(host, port, database, username, password)
        source.connection_status = "valid" if result.success else "invalid"
        source.last_validated_at = datetime.now(UTC)
        if not result.success:
            source.validation_error = result.message

        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return source

    async def update_source(
        self, source_id: UUID, auto_commit: bool = True, **kwargs
    ) -> Source | None:
        source = await self.get_source(source_id)
        if not source:
            return None

        connection_fields = {"source_type", "host", "port", "database", "username"}
        connection_changed = any(
            field in kwargs and kwargs[field] != getattr(source, field)
            for field in connection_fields
        )
        password = kwargs.pop("password", None)
        if "source_type" in kwargs and kwargs["source_type"] is not None:
            kwargs["source_type"] = str(kwargs["source_type"]).lower()
        if password is not None and password != "":
            connection_changed = True

        required_fields = {"name", "host", "port", "database", "username"}
        for key, value in kwargs.items():
            if value is None and key in required_fields:
                continue
            if hasattr(source, key):
                setattr(source, key, value)

        if password is not None and password != "":
            encrypted = await encrypt_password(self.session, password)
            if source.credential:
                source.credential.password_encrypted = encrypted
            else:
                credential = SourceCredential(
                    source_id=source.id, password_encrypted=encrypted
                )
                self.session.add(credential)

        if connection_changed:
            if source.credential:
                if password is not None and password != "":
                    plain_password = password
                else:
                    plain_password = await decrypt_password(
                        self.session, source.credential.password_encrypted
                    )
                if source.source_type == "s3":
                    result = await test_s3_connection(
                        source.host, source.port, source.database, source.username, plain_password
                    )
                else:
                    result = await test_connection(
                        source.host, source.port, source.database, source.username, plain_password
                    )
                source.connection_status = "valid" if result.success else "invalid"
                source.last_validated_at = datetime.now(UTC)
                source.validation_error = None if result.success else result.message

            # FR-006: source change pauses linked flows until validation/review.
            await self.session.execute(
                update(Flow)
                .where(
                    Flow.source_id == source_id,
                    Flow.deleted_at.is_(None),
                    Flow.status.in_(["paused", "running", "success", "failed"]),
                )
                .values(
                    status="paused",
                    status_reason="Параметры источника изменены. Проверьте источник и возобновите поток.",
                )
            )

        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return source

    async def delete_source(self, source_id: UUID, auto_commit: bool = True) -> bool:
        source = await self.get_source(source_id)
        if not source:
            return False

        flows_result = await self.session.execute(
            select(Flow.id).where(
                Flow.source_id == source_id,
                Flow.deleted_at.is_(None),
            )
        )
        flow_ids = [row[0] for row in flows_result.all()]

        if flow_ids:
            await RunService(self.session).cancel_active_runs_for_flows(
                flow_ids=flow_ids,
                reason="Запуск остановлен: источник удален.",
            )

        await self.session.execute(
            update(Flow)
            .where(
                Flow.source_id == source_id,
                Flow.deleted_at.is_(None),
            )
            .values(
                source_id=None,
                source_deleted=True,
                pause_requested=False,
                status="paused",
                status_reason="Источник удален. Запуск заблокирован до ручного удаления потока.",
            )
        )
        if flow_ids:
            await self.session.execute(
                update(Schedule)
                .where(Schedule.flow_id.in_(flow_ids))
                .values(
                    is_active=False,
                    next_run_at=None,
                )
            )

        await self.session.delete(source)
        if auto_commit:
            await self.session.commit()
        return True

    async def test_source_connection(self, source_id: UUID, auto_commit: bool = True) -> dict:
        source = await self.get_source(source_id)
        if not source or not source.credential:
            return {"success": False, "message": "Источник не найден"}

        password = await decrypt_password(self.session, source.credential.password_encrypted)
        if source.source_type == "s3":
            result = await test_s3_connection(
                source.host,
                source.port,
                source.database,
                source.username,
                password,
            )
        else:
            result = await test_connection(
                source.host,
                source.port,
                source.database,
                source.username,
                password,
            )

        source.connection_status = "valid" if result.success else "invalid"
        source.last_validated_at = datetime.now(UTC)
        source.validation_error = None if result.success else result.message
        if auto_commit:
            await self.session.commit()

        return {
            "success": result.success,
            "message": result.message,
            "server_version": result.server_version,
            "latency_ms": result.latency_ms,
        }
