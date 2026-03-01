"""Request validation error handling (T120)."""

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
import structlog

from src.core.config import settings

logger = structlog.get_logger()


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            })
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation error", "errors": errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        detail = exc.detail
        if not isinstance(detail, (str, list, dict)):
            detail = str(detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detail},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        error_id = uuid4().hex[:12]
        logger.error(
            "unhandled_exception",
            error_id=error_id,
            error=str(exc),
            error_type=exc.__class__.__name__,
            path=request.url.path,
        )

        if isinstance(exc, ValueError):
            return JSONResponse(status_code=400, content={"detail": str(exc)})

        if isinstance(exc, IntegrityError):
            detail = "Конфликт данных: запись уже существует или нарушены ограничения."
            if settings.debug:
                detail = f"{detail} {exc}"
            return JSONResponse(
                status_code=409,
                content={"detail": detail, "error_id": error_id},
            )

        if isinstance(exc, SQLAlchemyError):
            detail = "Ошибка базы данных. Повторите попытку или обратитесь к администратору."
            if settings.debug:
                detail = f"{detail} {exc}"
            return JSONResponse(
                status_code=500,
                content={"detail": detail, "error_id": error_id},
            )

        detail = "Внутренняя ошибка сервера. Повторите попытку или обратитесь к администратору."
        if settings.debug:
            detail = f"{detail} {exc}"
        return JSONResponse(
            status_code=500,
            content={"detail": detail, "error_id": error_id},
        )
