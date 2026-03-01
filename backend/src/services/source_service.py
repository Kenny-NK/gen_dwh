"""Source CRUD operations service (T040)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.flow import Flow
from src.models.source import Source
from src.models.source_credential import SourceCredential
from src.services.connection import decrypt_password, encrypt_password, test_connection


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
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        description: str | None = None,
        created_by: UUID | None = None,
    ) -> Source:
        source = Source(
            name=name,
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
        result = await test_connection(host, port, database, username, password)
        source.connection_status = "valid" if result.success else "invalid"
        source.last_validated_at = datetime.now(UTC)
        if not result.success:
            source.validation_error = result.message

        await self.session.flush()
        await self.session.commit()
        return source

    async def update_source(
        self, source_id: UUID, **kwargs
    ) -> Source | None:
        source = await self.get_source(source_id)
        if not source:
            return None

        connection_fields = {"host", "port", "database", "username"}
        connection_changed = any(
            field in kwargs and kwargs[field] != getattr(source, field)
            for field in connection_fields
        )
        password = kwargs.pop("password", None)
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
        await self.session.commit()
        return source

    async def delete_source(self, source_id: UUID) -> bool:
        source = await self.get_source(source_id)
        if not source:
            return False
        source.deleted_at = datetime.now(UTC)
        await self.session.commit()
        return True

    async def test_source_connection(self, source_id: UUID) -> dict:
        from src.services.connection import decrypt_password

        source = await self.get_source(source_id)
        if not source or not source.credential:
            return {"success": False, "message": "Источник не найден"}

        password = await decrypt_password(self.session, source.credential.password_encrypted)
        result = await test_connection(source.host, source.port, source.database, source.username, password)

        source.connection_status = "valid" if result.success else "invalid"
        source.last_validated_at = datetime.now(UTC)
        source.validation_error = None if result.success else result.message
        await self.session.commit()

        return {
            "success": result.success,
            "message": result.message,
            "server_version": result.server_version,
            "latency_ms": result.latency_ms,
        }
