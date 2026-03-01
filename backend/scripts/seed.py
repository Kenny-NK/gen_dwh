"""Database seed script for testing (T128)."""

import asyncio
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tenant import validate_schema_name
from src.models.base import SystemSessionLocal, system_engine, Base
from src.models.tenant import Tenant
from src.models.user import User


async def seed():
    """Create test tenant and user."""
    async with system_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SystemSessionLocal() as session:
        # Create test tenant
        tenant = Tenant(
            id=uuid4(),
            subdomain="acme",
            schema_name="tenant_acme",
            keycloak_realm="gendwh",
            name="Acme Corp",
        )
        session.add(tenant)
        await session.flush()

        # Create tenant schema
        schema_name = validate_schema_name(tenant.schema_name)
        await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))

        # Create test user
        user = User(
            tenant_id=tenant.id,
            keycloak_id="test-user-001",
            email="admin@acme.com",
            role="admin",
        )
        session.add(user)

        await session.commit()
        print(f"Created tenant: {tenant.name} (schema: {tenant.schema_name})")
        print(f"Created user: {user.email} (role: {user.role})")


if __name__ == "__main__":
    asyncio.run(seed())
