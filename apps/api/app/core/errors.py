from typing import Any

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse


class AppError(HTTPException):
    code: str = "internal_error"

    def __init__(self, message: str, *, status_code: int = 400, details: Any = None):
        super().__init__(status_code=status_code, detail=message)
        self.message = message
        self.details = details


class NotFound(AppError):
    code = "not_found"

    def __init__(self, message: str = "Not found", details: Any = None):
        super().__init__(message, status_code=status.HTTP_404_NOT_FOUND, details=details)


class Unauthorized(AppError):
    code = "unauthorized"

    def __init__(self, message: str = "Unauthorized", details: Any = None):
        super().__init__(message, status_code=status.HTTP_401_UNAUTHORIZED, details=details)


class Forbidden(AppError):
    code = "forbidden"

    def __init__(self, message: str = "Forbidden", details: Any = None):
        super().__init__(message, status_code=status.HTTP_403_FORBIDDEN, details=details)


class Conflict(AppError):
    code = "conflict"

    def __init__(self, message: str = "Conflict", details: Any = None):
        super().__init__(message, status_code=status.HTTP_409_CONFLICT, details=details)


def envelope_ok(data: Any) -> dict:
    return {"ok": True, "data": data}


def envelope_err(code: str, message: str, *, details: Any = None, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "data": None, "error": {"code": code, "message": message, "details": details}},
    )
