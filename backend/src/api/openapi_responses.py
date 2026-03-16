"""Reusable OpenAPI response models and helpers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    field: str = Field(description="Путь до невалидного поля")
    message: str = Field(description="Описание ошибки валидации")
    type: str = Field(description="Тип ошибки валидации")

    model_config = {
        "json_schema_extra": {
            "example": {
                "field": "body.name",
                "message": "Field required",
                "type": "missing",
            }
        }
    }


class ApiErrorResponse(BaseModel):
    detail: str | dict[str, Any] | list[dict[str, Any]] = Field(
        description="Описание ошибки; в некоторых endpoint'ах может быть объектом",
    )
    error_id: str | None = Field(
        default=None,
        description="Идентификатор ошибки для поиска в логах, если backend его сгенерировал",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "detail": "Источник не найден",
                "error_id": "9d4a7c0f1b2e",
            }
        }
    }


class ValidationErrorResponse(BaseModel):
    detail: str = Field(description="Общее описание ошибки валидации")
    errors: list[ValidationIssue] = Field(description="Список ошибок валидации")

    model_config = {
        "json_schema_extra": {
            "example": {
                "detail": "Validation error",
                "errors": [
                    {
                        "field": "body.port",
                        "message": "Input should be greater than or equal to 1",
                        "type": "greater_than_equal",
                    }
                ],
            }
        }
    }


def _json_response(
    *,
    model: type[BaseModel],
    description: str,
    example: dict[str, Any],
) -> dict[str, Any]:
    return {
        "model": model,
        "description": description,
        "content": {
            "application/json": {
                "example": example,
            }
        },
    }


def merge_openapi_responses(*groups: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    merged: dict[int, dict[str, Any]] = {}
    for group in groups:
        merged.update(group)
    return merged


RESPONSE_400_BAD_REQUEST = {
    400: _json_response(
        model=ApiErrorResponse,
        description="Некорректный запрос или бизнес-ошибка",
        example={"detail": "Некорректный запрос"},
    )
}

RESPONSE_401_UNAUTHORIZED = {
    401: _json_response(
        model=ApiErrorResponse,
        description="Пользователь не авторизован или сессия недействительна",
        example={"detail": "Не авторизован"},
    )
}

RESPONSE_403_FORBIDDEN = {
    403: _json_response(
        model=ApiErrorResponse,
        description="Недостаточно прав или нет доступа к ресурсу",
        example={"detail": "Недостаточно прав: требуется 'flows:write'"},
    )
}

RESPONSE_404_NOT_FOUND = {
    404: _json_response(
        model=ApiErrorResponse,
        description="Ресурс не найден",
        example={"detail": "Ресурс не найден"},
    )
}

RESPONSE_409_CONFLICT = {
    409: _json_response(
        model=ApiErrorResponse,
        description="Конфликт состояния или данных",
        example={"detail": "Запуск этого потока уже выполняется"},
    )
}

RESPONSE_422_VALIDATION = {
    422: _json_response(
        model=ValidationErrorResponse,
        description="Ошибка валидации входных данных",
        example={
            "detail": "Validation error",
            "errors": [
                {
                    "field": "body.source_type",
                    "message": "Input should be 'postgres', 's3' or 'jira'",
                    "type": "literal_error",
                }
            ],
        },
    )
}

RESPONSE_503_UNAVAILABLE = {
    503: _json_response(
        model=ApiErrorResponse,
        description="Внешняя зависимость или очередь временно недоступна",
        example={"detail": "Сервис авторизации временно недоступен"},
    )
}
