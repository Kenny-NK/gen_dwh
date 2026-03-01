# Quick Start: Data Pipeline MVP

**Feature**: 001-data-pipeline-mvp
**Date**: 2026-03-01

This guide covers local development setup and verification of the key user flow.

---

## Prerequisites

- Docker Desktop 24+ (with Docker Compose v2)
- Python 3.12+
- Node.js 20+
- pnpm 8+

---

## 1. Clone and Setup

```bash
# Clone repository
git clone <repo-url> gen_dwh
cd gen_dwh

# Copy environment file
cp docker/.env.example docker/.env

# Edit .env with your settings
# Required: DB passwords, encryption key, Keycloak secrets
```

### Environment Variables

```bash
# docker/.env
# PostgreSQL
POSTGRES_SYSTEM_PASSWORD=your_system_password
POSTGRES_BUSINESS_PASSWORD=your_business_password
DB_ENCRYPTION_KEY=your_32_byte_hex_key

# Redis
REDIS_PASSWORD=your_redis_password

# Keycloak
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=admin_password
KC_HOSTNAME=localhost

# Application
APP_SECRET_KEY=your_app_secret
KEYCLOAK_URL=http://keycloak:8080
KEYCLOAK_REALM=gendwh
KEYCLOAK_CLIENT_ID=gendwh-app
```

---

## 2. Start Infrastructure

```bash
# Start all services (databases, redis, keycloak)
docker compose -f docker/docker-compose.yml up -d postgres-system postgres-business redis keycloak

# Wait for services to be healthy (30-60 seconds)
docker compose -f docker/docker-compose.yml logs -f keycloak
# Wait for "Listening on: http://0.0.0.0:8080"
```

### Initialize Keycloak

```bash
# Access Keycloak Admin Console
open http://localhost:8080/admin
# Login: admin / admin_password

# Create realm:
# 1. Click "Create Realm"
# 2. Name: gendwh
# 3. Click "Create"

# Create client:
# 1. Go to Clients → Create Client
# 2. Client ID: gendwh-app
# 3. Client Authentication: On
# 4. Valid Redirect URIs: http://localhost:5173/*
# 5. Web Origins: http://localhost:5173

# Create client scope for tenant_id:
# 1. Go to Client Scopes → Create
# 2. Name: tenant_id
# 3. Add mapper: User Attribute
#    - User Attribute: tenant_id
#    - Token Claim Name: tenant_id
#    - Claim JSON Type: String

# Create test user:
# 1. Go to Users → Create User
# 2. Username: testuser
# 3. Email: test@example.com
# 4. Set password in Credentials tab
# 5. Add tenant_id attribute: "acme"
# 6. Assign role: View all roles → Select "admin" or "user"
```

---

## 3. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or: .\venv\Scripts\activate (Windows)

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run database migrations
alembic upgrade head

# Create test tenant
python scripts/create_tenant.py --subdomain acme --name "Acme Corp"

# Start development server
uvicorn src.main:app --reload --port 8000
```

### Verify Backend

```bash
# Health check
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","database":"ok","redis":"ok","meltano":"ok"}
```

---

## 4. Frontend Setup

```bash
cd frontend

# Install dependencies
pnpm install

# Start development server
pnpm dev
```

### Verify Frontend

```bash
# Open browser
open http://localhost:5173

# Should redirect to Keycloak login
# Login with: testuser / <password>
# Should redirect back to dashboard
```

---

## 5. Meltano Setup

```bash
cd meltano

# Install Meltano (if not in Docker)
pip install meltano

# Initialize project (already done, but for reference)
meltano install

# Verify installation
meltano discover extractors
# Should list tap-postgres

meltano discover loaders
# Should list target-postgres
```

---

## 6. Key User Flow Verification

This section walks through the primary user journey: **Create source → Configure flow → Preview → Run**.

### Step 1: Create Source Connection

```bash
# Get auth token (from Keycloak)
TOKEN=$(curl -s -X POST http://localhost:8080/realms/gendwh/protocol/openid-connect/token \
  -d "client_id=gendwh-app" \
  -d "client_secret=<your-client-secret>" \
  -d "username=testuser" \
  -d "password=<password>" \
  -d "grant_type=password" | jq -r .access_token)

# Create source
curl -X POST http://localhost:8000/api/v1/sources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test PostgreSQL",
    "host": "postgres-source.example.com",
    "port": 5432,
    "database": "source_db",
    "username": "source_user",
    "password": "source_password"
  }'

# Expected: 201 Created with source object
# Check connection_status: should be "valid" or "invalid" with error message
```

### Step 2: Configure Flow

```bash
# Get available schemas
curl http://localhost:8000/api/v1/sources/{source_id}/schemas \
  -H "Authorization: Bearer $TOKEN"

# Get tables in schema
curl http://localhost:8000/api/v1/sources/{source_id}/schemas/public/tables \
  -H "Authorization: Bearer $TOKEN"

# Create flow
curl -X POST http://localhost:8000/api/v1/flows \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Users Import",
    "source_id": "{source_id}",
    "target_schema": "tenant_acme",
    "write_mode": "upsert",
    "upsert_key": "id"
  }'

# Add table to flow
curl -X POST http://localhost:8000/api/v1/flows/{flow_id}/tables \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_schema": "public",
    "source_table": "users",
    "replication_method": "INCREMENTAL",
    "replication_key": "updated_at"
  }'
```

### Step 3: Preview Data

```bash
# Start preview
curl -X POST http://localhost:8000/api/v1/flows/{flow_id}/preview \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"row_limit": 100}'

# Check preview status (poll until completed)
curl http://localhost:8000/api/v1/flows/{flow_id}/preview/{session_id} \
  -H "Authorization: Bearer $TOKEN"

# Get preview data
curl "http://localhost:8000/api/v1/flows/{flow_id}/preview/{session_id}/data?table=users&page=1" \
  -H "Authorization: Bearer $TOKEN"
```

### Step 4: Configure Schedule and Run

```bash
# Set schedule
curl -X PUT http://localhost:8000/api/v1/flows/{flow_id}/schedule \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "schedule_type": "cron",
    "cron_expression": "0 */6 * * *",
    "timezone": "Europe/Moscow"
  }'

# Activate flow
curl -X POST http://localhost:8000/api/v1/flows/{flow_id}/activate \
  -H "Authorization: Bearer $TOKEN"

# Trigger manual run
curl -X POST http://localhost:8000/api/v1/flows/{flow_id}/runs \
  -H "Authorization: Bearer $TOKEN"

# Check run status
curl http://localhost:8000/api/v1/flows/{flow_id}/runs/{run_id} \
  -H "Authorization: Bearer $TOKEN"
```

### Step 5: Verify Data in Target

```bash
# Connect to business database
docker exec -it gen_dwh-postgres-business psql -U postgres -d business

# Check extracted data
SET search_path TO tenant_acme;
SELECT * FROM users LIMIT 10;
```

---

## 7. Running Tests

```bash
# Backend unit tests
cd backend
pytest tests/unit -v

# Backend integration tests (requires Docker)
pytest tests/integration -v --docker

# Frontend tests
cd frontend
pnpm test

# E2E tests (requires all services running)
cd frontend
pnpm test:e2e
```

---

## 8. Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Keycloak not starting | Wait 60s, check `docker logs gen_dwh-keycloak` |
| Database connection refused | Check passwords in .env match docker-compose.yml |
| Meltano command not found | Run `pip install meltano` in venv |
| Preview timeout | Increase `timeout_minutes` in schedule config |
| PII not masked | Check user role is 'user', not 'admin' |

### Logs

```bash
# Backend logs
docker logs gen_dwh-backend -f

# Celery worker logs
docker logs gen_dwh-celery-worker -f

# Scheduler logs
docker logs gen_dwh-celery-beat -f
```

---

## 9. Development Workflow

```bash
# Start all services for development
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d

# Backend with auto-reload
cd backend && uvicorn src.main:app --reload

# Frontend with hot reload
cd frontend && pnpm dev

# Run migrations after model changes
cd backend && alembic revision --autogenerate -m "description"
cd backend && alembic upgrade head
```
