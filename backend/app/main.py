"""FastAPI 앱 진입점. 실행: uvicorn app.main:app --reload (backend/에서)"""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import todos

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="My ToDo API", version="0.1.0")

    origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        # 내부 정보는 응답에 노출하지 않고 로그에만 남긴다 (api-spec 오류 응답 500)
        logger.exception("처리하지 못한 오류: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "서버 오류가 발생했습니다."})

    @app.get("/api/health", tags=["health"])
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(todos.router)
    return app


app = create_app()
