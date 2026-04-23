"""FastAPI 入口"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# 结构化日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("kb")

# 加载 .env
load_dotenv()

from app.api.routes import router

APP_ENV = os.getenv("APP_ENV", "development")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:8000")

app = FastAPI(
    title="知识库问答平台",
    description="基于 RAG 架构的智能知识库问答系统",
    version="0.1.0",
)

# 生产环境限定 CORS 域名，开发环境允许所有
if APP_ENV == "development":
    allow_origins = ["*"]
else:
    allow_origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"


# ─── 全局异常处理 ─────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"未处理异常 {request.method} {request.url.path}: {exc}", exc_info=True)
    # 数据库重复等已知错误，返回具体信息
    detail = str(exc)
    if "Duplicate entry" in detail or "UNIQUE constraint" in detail:
        return JSONResponse(status_code=400, content={"detail": "文件已存在，请勿重复上传"})
    return JSONResponse(
        status_code=500,
        content={"detail": f"服务器内部错误: {detail[:200]}"},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求日志中间件"""
    import time
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    # 只记录 API 请求
    if request.url.path.startswith("/api/"):
        logger.info(f"{request.method} {request.url.path} → {response.status_code} ({elapsed:.3f}s)")
    return response

app.include_router(router)

# 静态文件（CSS/JS）— 必须在 catch-all 之前
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
