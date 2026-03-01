"""Dashboard stats endpoint (T105)."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_tenant_db
from src.middleware.auth import get_current_user
from src.models.flow import Flow
from src.models.run import Run
from src.models.source import Source

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    # Sources count
    sources_result = await db.execute(
        select(func.count(Source.id)).where(Source.deleted_at.is_(None))
    )
    total_sources = sources_result.scalar() or 0

    # Flows by status
    flows_result = await db.execute(
        select(Flow.status, func.count(Flow.id))
        .where(Flow.deleted_at.is_(None))
        .group_by(Flow.status)
    )
    flows_by_status = dict(flows_result.fetchall())

    # Recent runs
    runs_result = await db.execute(
        select(Run.status, func.count(Run.id))
        .join(Flow, Flow.id == Run.flow_id)
        .where(Flow.deleted_at.is_(None))
        .group_by(Run.status)
    )
    runs_by_status = dict(runs_result.fetchall())

    # Total records processed
    records_result = await db.execute(
        select(func.sum(Run.records_processed))
        .join(Flow, Flow.id == Run.flow_id)
        .where(Run.status == "success", Flow.deleted_at.is_(None))
    )
    total_records = records_result.scalar() or 0

    return {
        "total_sources": total_sources,
        "flows_by_status": flows_by_status,
        "runs_by_status": runs_by_status,
        "total_records_processed": total_records,
    }
