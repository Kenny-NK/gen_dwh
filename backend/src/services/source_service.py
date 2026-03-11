"""Source CRUD operations service (T040)."""

from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.models.flow import Flow
from src.models.schedule import Schedule
from src.models.source import Source
from src.models.source_credential import SourceCredential
from src.schemas.jira import JiraExtractionConfig
from src.services.connection import (
    decrypt_password,
    encrypt_password,
    test_connection,
    test_s3_connection,
)
from src.services.jira_service import JiraService
from src.services.run_service import RunService


class SourceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _normalize_jira_auth_type(jira_auth_type: str | None) -> str:
        normalized = str(jira_auth_type or "").strip().lower()
        if normalized == "pat_bearer":
            return "pat_bearer"
        if normalized == "basic_password":
            return "basic_password"
        return "basic_token"

    @classmethod
    def _get_jira_auth_type(cls, extraction_config: dict | None) -> str:
        if not isinstance(extraction_config, dict):
            return "basic_token"
        return cls._normalize_jira_auth_type(extraction_config.get("auth_type"))

    @classmethod
    def _get_jira_runtime_engine(cls, extraction_config: dict | None) -> str:
        _ = cls._get_jira_auth_type(extraction_config)
        return "native"

    @classmethod
    def _build_jira_extraction_config(
        cls,
        extraction_config: dict | None,
        *,
        jira_auth_type: str,
    ) -> dict:
        payload = JiraExtractionConfig.model_validate(extraction_config or {}).model_dump(mode="json")
        payload["auth_type"] = cls._normalize_jira_auth_type(jira_auth_type)
        payload["runtime_engine"] = "native"
        return payload

    @staticmethod
    def _validate_source(
        source_type: str,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str | None,
        require_password: bool,
        jira_auth_type: str = "basic_token",
    ) -> None:
        normalized = (source_type or "postgres").lower()
        if normalized not in {"postgres", "s3", "jira"}:
            raise ValueError("Неподдерживаемый тип источника")
        if normalized == "jira" and not settings.jira_connector_enabled:
            raise ValueError("Jira connector is disabled")

        if require_password and not (password or "").strip():
            if normalized == "jira":
                raise ValueError("API token обязателен")
            raise ValueError("Пароль обязателен")

        if normalized == "jira":
            parsed = urlparse((host or "").strip())
            if parsed.scheme.lower() != "https" or not parsed.netloc:
                raise ValueError("Base URL должен быть валидным HTTPS URL")
            if jira_auth_type in {"basic_token", "basic_password"} and not (username or "").strip():
                raise ValueError("Логин Jira обязателен")
            if port and port != 443:
                raise ValueError("Для Jira должен использоваться HTTPS порт 443")
            return

        required = {
            "host": host,
            "database": database,
            "username": username,
        }
        for field, value in required.items():
            if not (value or "").strip():
                raise ValueError(f"Поле '{field}' обязательно")
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise ValueError("Некорректный порт")

    @staticmethod
    def _normalize_connection_fields(
        source_type: str,
        host: str,
        port: int,
        database: str,
        username: str,
    ) -> tuple[str, str, int, str, str]:
        normalized = (source_type or "postgres").lower()
        if normalized == "jira":
            return normalized, (host or "").strip().rstrip("/"), 443, "", (username or "").strip()
        return normalized, (host or "").strip(), int(port), (database or "").strip(), (username or "").strip()

    async def _run_connection_test(
        self,
        source_type: str,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        jira_auth_type: str = "basic_token",
    ) -> dict:
        normalized = (source_type or "postgres").lower()
        if normalized == "s3":
            result = await test_s3_connection(host, port, database, username, password)
            return {
                "success": result.success,
                "message": result.message,
                "server_version": result.server_version,
                "latency_ms": result.latency_ms,
            }
        if normalized == "jira":
            if not settings.jira_connector_enabled:
                return {
                    "success": False,
                    "message": "Jira connector is disabled by feature flag",
                    "error_type": "config",
                }
            try:
                async with JiraService(
                    host,
                    username,
                    password,
                    auth_type=jira_auth_type,
                ) as jira:
                    user_info = await jira.validate_jira_credentials()
                return {
                    "success": True,
                    "message": "Connection successful",
                    "user_info": user_info,
                }
            except Exception as exc:
                classified = JiraService.classify_error(exc)
                return {
                    "success": False,
                    "message": classified.message,
                    "error_type": classified.error_type,
                    "suggestion": classified.suggestion,
                }
        result = await test_connection(host, port, database, username, password)
        return {
            "success": result.success,
            "message": result.message,
            "server_version": result.server_version,
            "latency_ms": result.latency_ms,
        }

    async def list_sources(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Source]:
        query = select(Source).options(selectinload(Source.credential)).where(Source.deleted_at.is_(None))
        if status:
            query = query.where(Source.connection_status == status)
        query = query.order_by(Source.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_sources(self, status: str | None = None) -> int:
        query = select(func.count(Source.id)).where(Source.deleted_at.is_(None))
        if status:
            query = query.where(Source.connection_status == status)
        result = await self.session.execute(query)
        return int(result.scalar() or 0)

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
        jira_auth_type: str | None = None,
        description: str | None = None,
        created_by: UUID | None = None,
        auto_commit: bool = True,
    ) -> Source:
        normalized_source_type = (source_type or "postgres").lower()
        normalized_source_type, host, port, database, username = self._normalize_connection_fields(
            normalized_source_type, host, port, database, username
        )
        normalized_jira_auth_type = self._normalize_jira_auth_type(jira_auth_type)
        self._validate_source(
            normalized_source_type,
            host,
            port,
            database,
            username,
            password,
            require_password=True,
            jira_auth_type=normalized_jira_auth_type,
        )
        extraction_config_payload: dict | None = None
        if normalized_source_type == "jira":
            extraction_config_payload = self._build_jira_extraction_config(
                None,
                jira_auth_type=normalized_jira_auth_type,
            )

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
            extraction_config=extraction_config_payload,
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

        result = await self._run_connection_test(
            normalized_source_type,
            host,
            port,
            database,
            username,
            password,
            jira_auth_type=normalized_jira_auth_type,
        )
        source.connection_status = "valid" if result["success"] else "invalid"
        source.last_validated_at = datetime.now(UTC)
        if not result["success"]:
            source.validation_error = result["message"]

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
        current_jira_auth_type = self._get_jira_auth_type(source.extraction_config)
        next_jira_auth_type = self._normalize_jira_auth_type(
            kwargs.pop("jira_auth_type", current_jira_auth_type)
        )
        if "source_type" in kwargs and kwargs["source_type"] is not None:
            kwargs["source_type"] = str(kwargs["source_type"]).lower()
        connection_changed = any(
            field in kwargs and kwargs[field] != getattr(source, field)
            for field in connection_fields
        )
        password = kwargs.pop("password", None)
        if password is not None and password != "":
            connection_changed = True

        next_source_type = str(kwargs.get("source_type", source.source_type)).lower()
        next_host = str(kwargs.get("host", source.host))
        next_port = int(kwargs.get("port", source.port))
        next_database = str(kwargs.get("database", source.database))
        next_username = str(kwargs.get("username", source.username))
        next_source_type, next_host, next_port, next_database, next_username = (
            self._normalize_connection_fields(
                next_source_type,
                next_host,
                next_port,
                next_database,
                next_username,
            )
        )
        kwargs["source_type"] = next_source_type
        kwargs["host"] = next_host
        kwargs["port"] = next_port
        kwargs["database"] = next_database
        kwargs["username"] = next_username
        if next_source_type == "jira" and next_jira_auth_type != current_jira_auth_type:
            connection_changed = True

        existing_password: str | None = None
        if source.credential:
            existing_password = await decrypt_password(
                self.session,
                source.credential.password_encrypted,
            )
        password_for_validation = password if password is not None and password != "" else existing_password
        self._validate_source(
            next_source_type,
            next_host,
            next_port,
            next_database,
            next_username,
            password_for_validation,
            require_password=source.credential is None and not bool(password),
            jira_auth_type=next_jira_auth_type,
        )

        required_fields = {"name", "host", "port", "database", "username"}
        for key, value in kwargs.items():
            if value is None and key in required_fields:
                continue
            if hasattr(source, key):
                setattr(source, key, value)

        if (source.source_type or "").lower() == "jira":
            source.extraction_config = self._build_jira_extraction_config(
                source.extraction_config,
                jira_auth_type=next_jira_auth_type,
            )
        if (source.source_type or "").lower() != "jira":
            source.extraction_config = None

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
                result = await self._run_connection_test(
                    source.source_type,
                    source.host,
                    source.port,
                    source.database,
                    source.username,
                    plain_password,
                    jira_auth_type=next_jira_auth_type,
                )
                source.connection_status = "valid" if result["success"] else "invalid"
                source.last_validated_at = datetime.now(UTC)
                source.validation_error = None if result["success"] else result["message"]

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

    async def delete_source(
        self,
        source_id: UUID,
        *,
        hard_delete: bool = False,
        auto_commit: bool = True,
    ) -> bool:
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
        if str(source.source_type).lower() == "jira" and flow_ids:
            raise ValueError(
                "Нельзя удалить Jira-источник с активными потоками. Сначала удалите связанные потоки."
            )

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

        if hard_delete:
            await self.session.delete(source)
        else:
            source.deleted_at = datetime.now(UTC)
        if auto_commit:
            await self.session.commit()
        return True

    async def test_source_connection(self, source_id: UUID, auto_commit: bool = True) -> dict:
        source = await self.get_source(source_id)
        if not source or not source.credential:
            return {"success": False, "message": "Источник не найден"}

        password = await decrypt_password(self.session, source.credential.password_encrypted)
        jira_auth_type = self._get_jira_auth_type(source.extraction_config)
        result = await self._run_connection_test(
            source.source_type,
            source.host,
            source.port,
            source.database,
            source.username,
            password,
            jira_auth_type=jira_auth_type,
        )
        source.connection_status = "valid" if result["success"] else "invalid"
        source.last_validated_at = datetime.now(UTC)
        source.validation_error = None if result["success"] else result["message"]
        if auto_commit:
            await self.session.commit()

        return result

    async def test_connection_payload(
        self,
        source_type: str,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        jira_auth_type: str | None = None,
    ) -> dict:
        normalized_source_type = (source_type or "postgres").lower()
        normalized_source_type, host, port, database, username = self._normalize_connection_fields(
            normalized_source_type, host, port, database, username
        )
        normalized_jira_auth_type = self._normalize_jira_auth_type(jira_auth_type)
        self._validate_source(
            normalized_source_type,
            host,
            port,
            database,
            username,
            password,
            require_password=True,
            jira_auth_type=normalized_jira_auth_type,
        )
        return await self._run_connection_test(
            normalized_source_type,
            host,
            port,
            database,
            username,
            password,
            jira_auth_type=normalized_jira_auth_type,
        )

    async def update_extraction_config(
        self,
        source_id: UUID,
        extraction_config: dict,
        auto_commit: bool = True,
    ) -> Source | None:
        source = await self.get_source(source_id)
        if not source:
            return None
        if (source.source_type or "").lower() != "jira":
            raise ValueError("This endpoint is only available for Jira sources")

        auth_type = self._get_jira_auth_type(source.extraction_config)
        payload = JiraExtractionConfig.model_validate(extraction_config)
        payload.auth_type = auth_type
        resolver = JiraService(source.host, source.username, None, auth_type=auth_type)
        try:
            payload.streams = resolver.resolve_stream_dependencies(payload.streams)
        finally:
            await resolver.aclose()
        persisted = payload.model_dump(mode="json")
        persisted["runtime_engine"] = self._get_jira_runtime_engine({"auth_type": auth_type})
        source.extraction_config = persisted
        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return source
