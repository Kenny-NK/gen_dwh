# CHANGE_LOG

## Jira Connector v1 Plan

### Agreed Scope
1. First iteration covers only `issues`.
2. First iteration uses stable technical column names.
3. When `query_mode = "jql"`, basic filters are fully ignored.
4. Jira remains on two runtimes for now:
   - `native` for `pat_bearer`
   - `Meltano` for `basic_token` / `basic_password`
5. Derived metrics such as `Lead Time` are explicitly out of scope for this iteration.

### Target Result
1. Jira `issues` should no longer expose useful data only inside opaque `fields` JSON.
2. Jira preview should show normalized tabular columns for `issues`.
3. `Jira Extraction Config` should have two tabs:
   - `Базовые настройки`
   - `JQL запрос`
4. Preview and extraction behavior must depend on the active query mode.
5. Preview and extraction behavior must remain deterministic and production-safe.

### Backend Plan

#### 1. Jira extraction config contract
1. Extend `backend/src/schemas/jira.py` with `query_mode: Literal["basic", "jql"] = "basic"`.
2. Keep backward compatibility for existing saved configs.
3. Normalize empty `jql` values to `None`.
4. Normalize invalid or missing `query_mode` to `basic`.

#### 2. Effective query resolution
1. Add a dedicated helper to resolve effective Jira issue query parameters.
2. Rules:
   - `basic`: use `project_keys`, `start_date`, `incremental_enabled`, `replication_key`; ignore `jql`
   - `jql`: use only `jql`; ignore `project_keys`, `start_date`, and other basic filters at query layer
3. Use the same helper in preview and runtime extraction paths.

#### 3. Issue normalization layer
1. Add a dedicated normalization module for Jira issues.
2. Normalize raw Jira issues into a stable flat row contract.
3. v1 target columns:
   - `issue_id`
   - `issue_key`
   - `summary`
   - `status_name`
   - `status_category_name`
   - `issue_type_name`
   - `project_id`
   - `project_key`
   - `project_name`
   - `created`
   - `updated`
   - `resolved`
   - `reporter_account_id`
   - `reporter_display_name`
   - `assignee_account_id`
   - `assignee_display_name`
   - `priority_name`
   - `resolution_name`
   - `labels`
   - `components`
   - `fix_versions`
   - `parent_issue_key`
   - `fields_raw`
4. Preserve raw payload in `_raw` where raw storage is already used.
5. Do not expand custom Jira fields in v1.

#### 4. Jira API field selection
1. Expand requested Jira issue fields in `backend/src/services/jira_service.py`.
2. Use an explicit allowlist, not `*all`.
3. v1 field set:
   - `summary`
   - `status`
   - `issuetype`
   - `project`
   - `created`
   - `updated`
   - `resolved`
   - `reporter`
   - `assignee`
   - `priority`
   - `resolution`
   - `labels`
   - `components`
   - `fixVersions`
   - `parent`

#### 5. Preview refactor
1. Update Jira preview endpoint and service flow to return normalized rows for `issues`.
2. Preview response should include:
   - `success`
   - `streams`
   - `record_count`
   - `effective_query_mode`
   - `effective_jql`
   - `columns_by_stream`
   - `rows_by_stream`
   - `schema_by_stream`
3. Keep backward compatibility temporarily where needed.
4. Build columns from normalized schema/order, not from the first row.

#### 6. Native load path
1. Update `backend/src/services/jira_loader.py` for `issues`.
2. Replace generic flattening for Jira issues with dedicated issue normalization.
3. Write normalized issue columns into the target table.
4. Preserve `_raw` and store `fields_raw` explicitly.

#### 7. Meltano path constraint
1. Keep Jira on Meltano for `basic_token` / `basic_password` in v1.
2. Do not attempt deep `tap-jira` normalization in this iteration.
3. Preview can still be normalized because it uses backend Jira API service.
4. Fully normalized physical issue load is guaranteed in v1 only for `native` Jira runtime.

### Frontend Plan

#### 1. Jira Extraction Config tabs
1. Update `frontend/src/components/JiraConfig/JiraStreamSelector.tsx`.
2. Add tabs:
   - `Базовые настройки`
   - `JQL запрос`
3. Add `query_mode` into component state and persisted config.
4. `Базовые настройки` tab should include:
   - projects
   - streams
   - batch size
   - replication key
   - incremental
   - start date
5. `JQL запрос` tab should include:
   - textarea for JQL
   - streams selection
   - helper text explaining that basic filters are ignored in this mode
6. Switching tabs must not drop entered values.

#### 2. Preview behavior
1. Update `frontend/src/components/JiraConfig/JiraPreviewResults.tsx` and `frontend/src/services/jiraApi.ts`.
2. Preview request payload must include `query_mode`.
3. `basic` preview request should send basic filters.
4. `jql` preview request should send only:
   - `streams`
   - `jql`
   - `batch_size`
   - `query_mode`
5. Preview table should render from backend-supplied columns, not `Object.keys(firstRow)`.
6. Changing tab or Jira query settings must invalidate stale preview.

#### 3. FlowCreate integration
1. Update `frontend/src/pages/Flows/FlowCreate.tsx`.
2. Add `query_mode` to default Jira config.
3. Preserve `query_mode` when loading saved source extraction config.
4. Reset stale preview on Jira config changes.
5. Pass the full current Jira config into preview and flow creation.

### Tests

#### Backend
1. Unit tests for `JiraExtractionConfig` backward compatibility and normalization.
2. Unit tests for effective query precedence.
3. Unit tests for Jira issue normalization.
4. Integration tests for Jira preview in `basic` mode.
5. Integration tests for Jira preview in `jql` mode.
6. Integration tests verifying that `jql` mode ignores basic filters.
7. Native load tests verifying normalized issue columns in target tables.

#### Frontend
1. Component tests for tab switching and state persistence.
2. Tests for preview payload generation in `basic` mode.
3. Tests for preview payload generation in `jql` mode.
4. Tests for stale preview reset on config changes.
5. Tests for rendering preview columns from backend metadata.

### Explicit Non-Goals For This Iteration
1. `worklogs`, `issue_comments`, `changelogs`, and CAPEX-specific enrichment are out of scope.
2. Derived metrics such as `Lead Time` are out of scope.
3. Human-friendly business column labels from Excel are out of scope.
4. Custom Jira fields expansion is out of scope.
5. Full normalized load parity for Meltano Jira runtime is out of scope.

### Recommended Delivery Order
1. Backend Jira config and effective query rules.
2. Backend issue normalization layer.
3. Backend preview contract update.
4. Frontend tabs and preview behavior.
5. Native Jira load normalization.
6. Test coverage.
7. Documentation updates.
