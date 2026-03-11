<!--
============================================================================
SYNC IMPACT REPORT
============================================================================
Version change: 1.0.0 → 1.1.0

Modified principles: None renamed

Added sections:
  - Principle VII: UI-Consistent Connector Experience

Removed sections: None

Templates requiring updates:
  - .specify/templates/plan-template.md: ✅ Compatible (Constitution Check section exists)
  - .specify/templates/spec-template.md: ✅ Compatible (requirements section aligns)
  - .specify/templates/tasks-template.md: ✅ Compatible (phase structure supports principles)

Follow-up TODOs: None

Rationale for MINOR bump: New principle (VII) added without removing or
redefining existing principles. This materially expands guidance for
connector development.
============================================================================
-->

# GenDWH Constitution

## Core Principles

### I. Security-First Credential Management

All credentials, API keys, and connection secrets MUST be stored exclusively in the System PostgreSQL database with encryption at rest. Credentials MUST NEVER be:
- Logged in plain text
- Exposed in API responses
- Stored in environment variables for production deployments
- Committed to version control

**Rationale**: The service manages connections to external data sources with sensitive credentials. A breach would compromise all connected systems.

### II. Meltano-First Data Integration

All data source connectors and pipelines MUST be created and managed through Meltano. Direct database connections to external sources are prohibited except through Meltano extractors. Pipeline configurations MUST be:
- Version-controlled
- Documented with schema expectations
- Testable in isolation

**Rationale**: Meltano provides standardized, maintainable data extraction with built-in logging, error handling, and scheduling. Custom connectors increase maintenance burden.

### III. Dual-Database Separation

The System PostgreSQL and Business PostgreSQL databases MUST remain strictly separated:
- **System DB**: Credentials, user accounts, source configurations, pipeline metadata, audit logs
- **Business DB**: Extracted data, transformed datasets, user-visible data

Cross-database queries are prohibited. Data transfer between databases MUST go through the application layer.

**Rationale**: Security isolation prevents accidental credential exposure through business queries. Different backup and access policies may apply to each database.

### IV. API-First Backend Architecture

The FastAPI backend MUST expose all functionality through versioned REST API endpoints. The React frontend MUST interact with the backend exclusively through these APIs. Direct database access from the frontend is prohibited. API contracts MUST be:
- Documented with OpenAPI/Swagger
- Versioned (e.g., `/api/v1/`)
- Backward-compatible for minor versions

**Rationale**: API-first design enables future mobile clients, CLI tools, or third-party integrations without backend changes.

### V. Containerized Deployment

All services MUST be deployable via Docker Compose. Each service MUST have:
- A dedicated Dockerfile with explicit version tags
- Health check endpoints
- Graceful shutdown handling
- Environment-based configuration (no hardcoded values)

**Rationale**: Docker Compose ensures consistent development and production environments, simplifies deployment, and enables horizontal scaling.

### VI. Observable Pipelines

All data pipelines MUST emit structured logs and metrics. Each pipeline run MUST record:
- Start/end timestamps
- Records processed count
- Error count and details
- Source/target identifiers

Pipeline status MUST be queryable through the API and visible in the UI.

**Rationale**: Data pipeline failures must be detectable and debuggable without SSH access to servers.

### VII. UI-Consistent Connector Experience

All data source connectors MUST follow a unified UX flow through the web interface. Every connector MUST provide:

1. **Credential Configuration UI**: Users MUST be able to input and save connection credentials (URL, authentication tokens, API keys) through a dedicated form in the UI. No manual configuration files or CLI commands required.

2. **Loading Parameters UI**: Users MUST be able to configure data loading settings (projects, entities, filters, date ranges, incremental options) through UI controls. All connector-specific options MUST be exposed as form fields.

3. **Preview Before Commit**: Users MUST be able to preview data BEFORE creating a flow. The preview MUST validate connectivity, show sample data, and confirm configuration correctness. Failed previews MUST display actionable error messages.

4. **Flow Creation Flow**: After successful preview, users MUST be able to create a data flow using the same wizard/process as existing connectors. No connector-specific deviation in the flow creation UX.

**Non-Negotiable Requirements**:
- Zero manual configuration outside the UI for end-to-end connector setup
- Consistent error handling and validation patterns across all connectors
- Preview MUST work for any connector before flow is persisted
- Connector-specific settings MUST be documented in the UI (tooltips, help text)

**Rationale**: Consistent UX reduces training overhead and enables non-technical users to configure new data sources without engineering support. Deviations create confusion and increase support burden.

## Technology Stack

### Mandatory Technologies

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend | React + TypeScript | 18.x / 5.x |
| Backend | Python + FastAPI | 3.11+ / 0.100+ |
| Data Integration | Meltano | 3.x |
| System Database | PostgreSQL | 15+ |
| Business Database | PostgreSQL | 15+ |
| Container Runtime | Docker + Docker Compose | 24+ / 2.x |

### Supported Connectors

| Source Type | Meltano Tap | UI Support |
|-------------|-------------|------------|
| PostgreSQL | tap-postgres | Full UI flow |
| S3 (CSV/XLSX) | tap-s3-csv | Full UI flow |
| Jira | tap-jira | Full UI flow (planned) |

### Technology Decisions

- **ORM**: SQLAlchemy (async where possible)
- **Migrations**: Alembic
- **Frontend State**: React Query for server state, Zustand for client state
- **UI Components**: To be determined per feature requirements
- **Testing**: pytest (backend), Vitest + React Testing Library (frontend)

## Data Architecture

### System Database Schema

Core entities that MUST exist in System PostgreSQL:
- `users` - User accounts
- `data_sources` - Registered external data sources
- `source_credentials` - Encrypted connection credentials
- `pipelines` - Meltano pipeline configurations
- `pipeline_runs` - Execution history and status
- `audit_logs` - Security-relevant actions

### Business Database Schema

Dynamic schema based on extracted data. Tables are created by Meltano loaders based on source structure.

### Data Flow

```
External Sources → Meltano Extractors → FastAPI Orchestration → Business PostgreSQL
                                    ↓
                              System PostgreSQL (metadata, credentials)
```

## Governance

### Amendment Procedure

1. Constitution changes MUST be proposed via pull request
2. Changes require review and approval from project maintainers
3. MAJOR version bumps require migration plan documentation
4. All dependent templates MUST be updated before merge

### Compliance Verification

- All PRs MUST pass constitution compliance check (manual or automated)
- New features MUST reference applicable principles in spec.md
- Complexity beyond defined principles MUST be justified in plan.md

### Version Policy

- **MAJOR**: Backward incompatible principle removals or redefinitions
- **MINOR**: New principles or materially expanded guidance
- **PATCH**: Clarifications, wording fixes, non-semantic refinements

**Version**: 1.1.0 | **Ratified**: 2026-02-26 | **Last Amended**: 2026-03-05
