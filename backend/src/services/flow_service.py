"""Flow CRUD operations service (T058)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.flow import Flow
from src.models.flow_table import FlowTable
from src.models.source import Source


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
        created_by: UUID | None = None,
    ) -> Flow:
        source_exists = await self.session.execute(
            select(Source.id).where(
                Source.id == source_id,
                Source.deleted_at.is_(None),
            )
        )
        if source_exists.scalar_one_or_none() is None:
            raise ValueError("Источник не найден")

        flow = Flow(
            name=name,
            source_id=source_id,
            target_schema=target_schema,
            write_mode=write_mode,
            description=description,
            target_table_prefix=target_table_prefix,
            upsert_key=upsert_key,
            created_by=created_by,
            status="draft",
        )
        self.session.add(flow)
        await self.session.flush()
        await self.session.commit()
        return flow

    async def update_flow(self, flow_id: UUID, **kwargs) -> Flow | None:
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
        await self.session.commit()
        return flow

    async def delete_flow(self, flow_id: UUID) -> bool:
        flow = await self.get_flow(flow_id)
        if not flow:
            return False
        flow.deleted_at = datetime.now(UTC)
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
    ) -> FlowTable:
        flow_table = FlowTable(
            flow_id=flow_id,
            source_schema=source_schema,
            source_table=source_table,
            target_table=target_table or source_table,
            replication_method=replication_method,
            replication_key=replication_key,
            selected_columns=selected_columns,
        )
        self.session.add(flow_table)
        try:
            await self.session.flush()
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if "flow_id" in str(exc).lower() and "source_schema" in str(exc).lower():
                raise ValueError("Таблица уже добавлена в поток")
            raise
        return flow_table

    async def update_table(self, table_id: UUID, **kwargs) -> FlowTable | None:
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
        await self.session.commit()
        return flow_table

    async def remove_table(self, table_id: UUID, flow_id: UUID | None = None) -> bool:
        query = select(FlowTable).where(FlowTable.id == table_id)
        if flow_id:
            query = query.where(FlowTable.flow_id == flow_id)
        result = await self.session.execute(query)
        flow_table = result.scalar_one_or_none()
        if not flow_table:
            return False
        await self.session.delete(flow_table)
        await self.session.commit()
        return True

    async def activate_flow(self, flow_id: UUID) -> Flow | None:
        flow = await self.get_flow(flow_id)
        if not flow or flow.status != "draft":
            return None
        flow.status = "paused"
        await self.session.flush()
        await self.session.commit()
        return flow
