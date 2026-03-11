# Jira Connector

## Overview

`jira` source type adds Jira Cloud extraction via Meltano `tap-jira`.

Supported flow:
1. Create or edit source in UI (`Sources -> New Source`, type `Jira`)
2. Validate credentials (`Base URL`, `Email`, `API token`)
3. Configure extraction (projects, streams, incremental settings)
4. Run preview
5. Create flow from preview

## Source Fields

- `host`: Jira base URL (`https://<company>.atlassian.net`)
- `port`: always `443`
- `username`: Jira email
- `password`: Jira API token (encrypted in `source_credentials`)
- `extraction_config`: JSON with streams/projects/batch/jql/incremental options

## API Endpoints

- `GET /api/v1/sources/{source_id}/jira/projects`
- `GET /api/v1/sources/{source_id}/jira/streams`
- `GET /api/v1/sources/{source_id}/jira/streams/{name}/schema`
- `PATCH /api/v1/sources/{source_id}/extraction-config`
- `POST /api/v1/sources/{source_id}/jira/preview`

## Feature Flag

- `JIRA_CONNECTOR_ENABLED=true` (backend env, enabled by default)

## Notes

- Deleting Jira source with active flows is blocked.
- Credentials changes are audited with redacted payload.
- Existing `postgres` and `s3` source behavior is preserved.

