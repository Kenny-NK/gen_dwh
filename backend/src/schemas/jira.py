"""Jira connector schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class JiraProject(BaseModel):
    id: str
    key: str
    name: str
    lead_display_name: str | None = None
    lead_account_id: str | None = None


class JiraExtractionConfig(BaseModel):
    auth_type: Literal["basic_token", "basic_password", "pat_bearer"] = "basic_token"
    query_mode: Literal["basic", "jql"] = "basic"
    streams: list[str] = Field(default_factory=lambda: ["issues"])
    start_date: datetime | None = None
    batch_size: int = Field(default=100, ge=1, le=1000)
    project_keys: list[str] = Field(default_factory=list)
    incremental_enabled: bool = False
    replication_key: str = "updated"
    jql: str | None = None

    @field_validator("auth_type", mode="before")
    @classmethod
    def _normalize_auth_type(cls, value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        if normalized == "pat_bearer":
            return "pat_bearer"
        if normalized == "basic_password":
            return "basic_password"
        if normalized in {"basic", "basic_token", ""}:
            return "basic_token"
        return normalized

    @field_validator("query_mode", mode="before")
    @classmethod
    def _normalize_query_mode(cls, value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        if normalized == "jql":
            return "jql"
        return "basic"

    @field_validator("streams")
    @classmethod
    def _validate_streams(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("At least one stream must be selected")
        deduplicated: list[str] = []
        for item in value:
            normalized = str(item).strip().lower()
            if not normalized:
                continue
            if normalized not in deduplicated:
                deduplicated.append(normalized)
        if not deduplicated:
            raise ValueError("At least one stream must be selected")
        return deduplicated

    @field_validator("jql", mode="before")
    @classmethod
    def _normalize_jql(cls, value: str | None) -> str | None:
        text = str(value or "").strip()
        return text or None

    @model_validator(mode="before")
    @classmethod
    def _infer_legacy_query_mode(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        if "query_mode" not in value and str(value.get("jql") or "").strip():
            return {**value, "query_mode": "jql"}
        return value


class JiraStreamMetadata(BaseModel):
    name: str
    display_name: str
    description: str
    replication_method: Literal["INCREMENTAL", "FULL_TABLE"]
    replication_keys: list[str] = Field(default_factory=list)
    primary_keys: list[str] = Field(default_factory=list)
    parent_stream: str | None = None
    field_count: int = 0
    stream_schema: dict | None = Field(default=None, alias="schema")

    model_config = {"populate_by_name": True}


class JiraErrorResponse(BaseModel):
    message: str
    error_type: Literal["auth", "network", "config", "runtime"]
    suggestion: str | None = None
