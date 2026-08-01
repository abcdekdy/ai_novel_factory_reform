"""
AI 小说工厂 - FastAPI 后端入口
启动: uvicorn main:app --reload --port 8765
"""
import sys
import io
import logging
import traceback
from contextlib import asynccontextmanager

# 强制 UTF-8 输出，防止 Windows 下管道编码不匹配导致终端中文乱码（锟斤拷）
if hasattr(sys.stdout, 'buffer') and sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import pipeline as pipeline_router
from api import projects as projects_router
from api import config as config_router
from api import events as events_router
from api.events import event_broker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("novel-factory")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("AI 小说工厂后端启动")
    yield
    logger.info("AI 小说工厂后端关闭")


app = FastAPI(
    title="AI 小说工厂 API",
    version="2.0.0",
    lifespan=lifespan,
)


# 全局异常处理器 — 确保未捕获异常返回具体原因而非 generic 500
@app.exception_handler(Exception)
async def universal_exception_handler(request: Request, exc: Exception):
    logger.exception(f"未捕获异常 {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "type": type(exc).__name__,
            "trace": traceback.format_exc().splitlines()[-3:] if app.debug else None,
        },
    )

# CORS — 开发模式下允许 Vite 开发服务器
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(events_router.router, prefix="/api/events", tags=["events"])
app.include_router(pipeline_router.router, prefix="/api/pipeline", tags=["pipeline"])
app.include_router(projects_router.router, prefix="/api/projects", tags=["projects"])
app.include_router(config_router.router, prefix="/api/config", tags=["config"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
