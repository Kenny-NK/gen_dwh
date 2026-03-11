"""Flow CRUD operations service (T058)."""

import logging
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.db_utils import quote_ident
from src.models.cleanup_job import CleanupJob
from src.models.flow import Flow
from src.models.flow_table import FlowTable
from src.models.source import Source
from src.models.base import BusinessSessionLocal
from src.schemas.jira import JiraExtractionConfig

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
logger = logging.getLogger(__name__)


class FlowService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_flows(
        self,
        status: str | None = None,
        source_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Flow]:
        query = (
            select(Flow)
            .options(selectinload(Flow.tables))
            .where(Flow.deleted_at.is_(None))
        )
        if status:
            query = query.where(Flow.status == status)
        if source_id:
            query = query.where(Flow.source_id == source_id)
        query = query.order_by(Flow.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_flows(
        self,
        status: str | None = None,
        source_id: UUID | None = None,
    ) -> int:
        query = select(func.count(Flow.id)).where(Flow.deleted_at.is_(None))
        if status:
            query = query.where(Flow.status == status)
        if source_id:
            query = query.where(Flow.source_id == source_id)
        result = await self.session.execute(query)
        return int(result.scalar() or 0)

    async def get_flow(self, flow_id: UUID) -> Flow | None:
        query = (
            select(Flow)
            .options(
                selectinload(Flow.tables),
                selectinload(Flow.schedule),
                selectinload(Flow.source).selectinload(Source.credential),
            )
            .where(Flow.id == flow_id, Flow.deleted_at.is_(None))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_flow(
        self,
        name: str,
        source_id: UUID,
        target_schema: str,
        write_mode: str = "append",
        description: str | None = None,
        target_table_prefix: str | None = None,
        upsert_key: str | None = None,
        extraction_config: dict | None = None,
        preview_mode: str = "auto",
        created_by: UUID | None = None,
        auto_commit: bool = True,
    ) -> Flow:
        source_result = await self.session.execute(
            select(Source).where(
                Source.id == source_id,
                Source.deleted_at.is_(None),
            )
        )
        source = source_result.scalar_one_or_none()
        if source is None:
            raise ValueError("Источник не найден")

        flow_extraction_config: dict | None = None
        if (source.source_type or "").lower() == "jira":
            source_extraction = source.extraction_config if isinstance(source.extraction_config, dict) else {}
            payload = JiraExtractionConfig.model_validate(extraction_config or {}).model_dump(mode="json")
            if source_extraction.get("auth_type"):
                payload["auth_type"] = source_extraction["auth_type"]
            flow_extraction_config = payload

        flow = Flow(
            name=name,
            source_id=source_id,
            target_schema=target_schema,
            write_mode=write_mode,
            description=description,
            target_table_prefix=target_table_prefix,
            upsert_key=upsert_key,
            extraction_config=flow_extraction_config,
            preview_mode=str(preview_mode or "auto").strip().lower() or "auto",
            created_by=created_by,
            status="draft",
        )
        self.session.add(flow)
        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return flow

    async def update_flow(self, flow_id: UUID, auto_commit: bool = True, **kwargs) -> Flow | None:
        flow = await self.get_flow(flow_id)
        if not flow:
            return None
        required_fields = {"name", "target_schema", "write_mode"}
        for key, value in kwargs.items():
            if value is None and key in required_fields:
                continue
            if hasattr(flow, key):
                setattr(flow, key, value)
        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return flow

    async def delete_flow(
        self,
        flow_id: UUID,
        drop_target_tables: bool = False,
        auto_commit: bool = True,
        ) -> bool:
        flow = await self.get_flow(flow_id)
        if not flow:
            return False
        flow.deleted_at = datetime.now(UTC)
        if auto_commit:
            await self.session.commit()
        return True

    async def add_table(
        self,
        flow_id: UUID,
        source_schema: str,
        source_table: str,
        target_table: str | None = None,
        replication_method: str = "FULL_TABLE",
        replication_key: str | None = None,
        selected_columns: list[str] | None = None,
        auto_commit: bool = True,
    ) -> FlowTable:
        flow = await self.get_flow(flow_id)
        if not flow:
            raise ValueError("Поток не найден")

        if target_table and target_table.strip():
            resolved_target_table = self._resolve_requested_target_table(
                source_table=source_table,
                requested_target_table=target_table,
                table_prefix=flow.target_table_prefix,
                source_type=getattr(flow.source, "source_type", None),
            )
        else:
            resolved_target_table = self._build_prefixed_target_table_name(
                source_table=source_table,
                table_prefix=flow.target_table_prefix,
            )

        flow_table = FlowTable(
            flow_id=flow_id,
            source_schema=source_schema,
            source_table=source_table,
            target_table=resolved_target_table,
            replication_method=replication_method,
            replication_key=replication_key,
            selected_columns=selected_columns,
        )
        self.session.add(flow_table)
        try:
            await self.session.flush()
            if auto_commit:
                await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if "flow_id" in str(exc).lower() and "source_schema" in str(exc).lower():
                raise ValueError("Таблица уже добавлена в поток")
            raise
        return flow_table

    @staticmethod
    def _normalize_table_identifier(raw_value: str | None, fallback: str = "table") -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_]+", "_", (raw_value or "").strip()).strip("_").lower()
        if not sanitized:
            sanitized = fallback
        if not sanitized:
            return ""
        if sanitized[0].isdigit():
            sanitized = f"t_{sanitized}"
        return sanitized[:63]

    @staticmethod
    def _default_target_table_name(source_table: str) -> str:
        """Normalize source identifier into a valid PostgreSQL table name."""
        base = source_table.strip().split("/")[-1]
        if "." in base:
            base = base.rsplit(".", 1)[0]
        return FlowService._normalize_table_identifier(base, fallback="table")

    @staticmethod
    def _build_prefixed_target_table_name(source_table: str, table_prefix: str | None) -> str:
        base = FlowService._default_target_table_name(source_table)
        prefix = FlowService._normalize_table_identifier(table_prefix, fallback="")
        if not prefix:
            return base
        if base == prefix or base.startswith(f"{prefix}_"):
            return base
        return FlowService._normalize_table_identifier(f"{prefix}_{base}", fallback=base)

    @classmethod
    def _resolve_requested_target_table(
        cls,
        *,
        source_table: str,
        requested_target_table: str | None,
        table_prefix: str | None,
        source_type: str | None,
    ) -> str:
        normalized_requested = cls._normalize_table_identifier(
            requested_target_table,
            fallback=cls._default_target_table_name(source_table),
        )
        if str(source_type or "").strip().lower() != "jira":
            return normalized_requested

        normalized_prefix = cls._normalize_table_identifier(table_prefix, fallback="")
        if not normalized_prefix:
            return normalized_requested

        default_target = cls._default_target_table_name(source_table)
        if normalized_requested in {default_target, str(source_table or "").strip().lower()}:
            return cls._build_prefixed_target_table_name(source_table, table_prefix)
        return normalized_requested

    async def update_table(self, table_id: UUID, **kwargs) -> FlowTable | None:
        auto_commit = kwargs.pop("auto_commit", True)
        flow_id = kwargs.pop("flow_id", None)
        query = select(FlowTable).where(FlowTable.id == table_id)
        if flow_id:
            query = query.where(FlowTable.flow_id == flow_id)
        result = await self.session.execute(query)
        flow_table = result.scalar_one_or_none()
        if not flow_table:
            return None
        for key, value in kwargs.items():
            if hasattr(flow_table, key):
                setattr(flow_table, key, value)
        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return flow_table

    async def remove_table(
        self,
        table_id: UUID,
        flow_id: UUID | None = None,
        drop_target_table: bool = False,
        auto_commit: bool = True,
    ) -> bool:
        query = select(FlowTable).where(FlowTable.id == table_id)
        if flow_id:
            query = query.where(FlowTable.flow_id == flow_id)
        result = await self.session.execute(query)
        flow_table = result.scalar_one_or_none()
        if not flow_table:
            return False
        await self.session.delete(flow_table)
        if auto_commit:
            await self.session.commit()
        return True

    async def activate_flow(self, flow_id: UUID, auto_commit: bool = True) -> Flow | None:
        flow = await self.get_flow(flow_id)
        if not flow or flow.status != "draft":
            return None
        flow.status = "paused"
        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return flow

    @staticmethod
    def _validate_identifier(value: str, field: str) -> str:
        if not _IDENTIFIER_RE.fullmatch(value):
            raise ValueError(f"Invalid {field}")
        return value

    async def _drop_target_table(self, schema_name: str, table_name: str) -> None:
        schema = self._validate_identifier(schema_name, "schema")
        table = self._validate_identifier(table_name, "table")
        async with BusinessSessionLocal() as business_session:
            await business_session.execute(
                text(f"DROP TABLE IF EXISTS {quote_ident(schema)}.{quote_ident(table)}")
            )
            await business_session.commit()

    async def _is_table_referenced_by_other_flows(
        self,
        *,
        schema_name: str,
        table_name: str,
        exclude_flow_id: UUID | None = None,
    ) -> bool:
        query = (
            select(FlowTable.id)
            .join(Flow, Flow.id == FlowTable.flow_id)
            .where(
                FlowTable.target_table == table_name,
                Flow.target_schema == schema_name,
                Flow.deleted_at.is_(None),
            )
            .limit(1)
        )
        if exclude_flow_id is not None:
            query = query.where(Flow.id != exclude_flow_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None

    def _build_drop_candidates(self, flow: Flow, flow_table: FlowTable) -> list[str]:
        candidates: list[str] = []

        def _add(candidate: str | None) -> None:
            value = (candidate or "").strip()
            if not value:
                return
            if value not in candidates:
                candidates.append(value)

        # Preferred name from flow configuration.
        _add(flow_table.target_table)

        source_type = (getattr(flow.source, "source_type", "") or "").lower()
        if source_type == "postgres":
            # Legacy compatibility: historical runs could write without target mapping.
            _add(flow_table.source_table)
            _add(self._default_target_table_name(flow_table.source_table))
        if source_type == "jira":
            _add(self._build_prefixed_target_table_name(flow_table.source_table, flow.target_table_prefix))

        return candidates

    async def _build_cleanup_plan(
        self,
        *,
        flow: Flow,
        flow_tables: list[FlowTable],
        exclude_flow_id: UUID | None,
    ) -> list[tuple[str, str]]:
        plan: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for flow_table in flow_tables:
            for candidate in self._build_drop_candidates(flow, flow_table):
                key = (flow.target_schema, candidate)
                if key in seen:
                    continue
                seen.add(key)
                if not _IDENTIFIER_RE.fullmatch(candidate):
                    logger.warning(
                        "Skipping cleanup for invalid table identifier '%s' (flow_id=%s)",
                        candidate,
                        flow.id,
                    )
                    continue
                if await self._is_table_referenced_by_other_flows(
                    schema_name=flow.target_schema,
                    table_name=candidate,
                    exclude_flow_id=exclude_flow_id,
                ):
                    logger.info(
                        "Skipping cleanup for %s.%s because it is referenced by another active flow",
                        flow.target_schema,
                        candidate,
                    )
                    continue
                plan.append(key)
        return plan

    async def build_flow_cleanup_plan(self, flow: Flow) -> list[tuple[str, str]]:
        return await self._build_cleanup_plan(
            flow=flow,
            flow_tables=list(flow.tables),
            exclude_flow_id=flow.id,
        )

    async def build_flow_table_cleanup_plan(
        self,
        flow: Flow,
        flow_table: FlowTable,
    ) -> list[tuple[str, str]]:
        return await self._build_cleanup_plan(
            flow=flow,
            flow_tables=[flow_table],
            exclude_flow_id=flow.id,
        )

    async def execute_cleanup_plan(self, cleanup_plan: list[tuple[str, str]]) -> None:
        for schema_name, table_name in cleanup_plan:
            if await self._is_table_referenced_by_other_flows(
                schema_name=schema_name,
                table_name=table_name,
            ):
                logger.info(
                    "Skipping cleanup for %s.%s because it is now referenced by an active flow",
                    schema_name,
                    table_name,
                )
                continue
            await self._drop_target_table(schema_name, table_name)

    async def enqueue_cleanup_jobs(
        self,
        cleanup_plan: list[tuple[str, str]],
        *,
        requested_by: UUID | None,
        related_entity_type: str,
        related_entity_id: UUID,
        auto_commit: bool = True,
    ) -> list[CleanupJob]:
        jobs: list[CleanupJob] = []
        seen: set[tuple[str, str]] = set()
        for schema_name, table_name in cleanup_plan:
            schema = self._validate_identifier(schema_name, "schema")
            table = self._validate_identifier(table_name, "table")
            key = (schema, table)
            if key in seen:
                continue
            seen.add(key)
            job = CleanupJob(
                job_type="drop_table",
                status="pending",
                target_schema=schema,
                target_table=table,
                requested_by=requested_by,
                related_entity_type=related_entity_type,
                related_entity_id=related_entity_id,
            )
            self.session.add(job)
            jobs.append(job)
        if not jobs:
            return []
        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return jobs

    async def _drop_flow_table_targets(self, flow: Flow, flow_table: FlowTable) -> None:
        for candidate in self._build_drop_candidates(flow, flow_table):
            if not _IDENTIFIER_RE.fullmatch(candidate):
                logger.warning(
                    "Skipping drop for invalid table identifier '%s' (flow_id=%s)",
                    candidate,
                    flow.id,
                )
                continue
            if await self._is_table_referenced_by_other_flows(
                schema_name=flow.target_schema,
                table_name=candidate,
                exclude_flow_id=flow.id,
            ):
                logger.info(
                    "Skipping drop for %s.%s because it is referenced by another active flow",
                    flow.target_schema,
                    candidate,
                )
                continue
            await self._drop_target_table(flow.target_schema, candidate)

    async def _drop_flow_target_tables(self, flow: Flow) -> None:
        seen: set[tuple[str, str]] = set()
        for table in flow.tables:
            for candidate in self._build_drop_candidates(flow, table):
                key = (flow.target_schema, candidate)
                if key in seen:
                    continue
                seen.add(key)
                if not _IDENTIFIER_RE.fullmatch(candidate):
                    logger.warning(
                        "Skipping drop for invalid table identifier '%s' (flow_id=%s)",
                        candidate,
                        flow.id,
                    )
                    continue
                if await self._is_table_referenced_by_other_flows(
                    schema_name=flow.target_schema,
                    table_name=candidate,
                    exclude_flow_id=flow.id,
                ):
                    logger.info(
                        "Skipping drop for %s.%s because it is referenced by another active flow",
                        flow.target_schema,
                        candidate,
                    )
                    continue
                await self._drop_target_table(flow.target_schema, candidate)
