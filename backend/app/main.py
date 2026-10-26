"""FastAPI 入口。"""

import asyncio
import time
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database import init_db, get_db
from app.api import tasks, uploads, ws, sessions, styles
from app.api import settings as settings_api
from app.logger import logger
from app.services.graph import get_node_stats


# ─── 监控数据（内存累积，重启归零）────────────────────────
_request_stats = {"total": 0, "errors": 0, "total_time_ms": 0.0, "slow_requests": 0}


async def _cleanup_old_files():
    """后台定时任务：每 24 小时清理 7 天前的上传和结果文件。"""
    while True:
        await asyncio.sleep(24 * 3600)
        try:
            cutoff = datetime.now() - timedelta(days=7)
            cleaned = 0
            for directory in [settings.upload_dir, settings.result_dir]:
                for f in directory.iterdir():
                    if f.is_file() and f.stat().st_mtime < cutoff.timestamp():
                        f.unlink()
                        cleaned += 1
            if cleaned > 0:
                logger.info("定时清理：删除 %d 个过期文件", cleaned)
        except Exception as e:
            logger.error("定时清理失败：%s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库 + RAG 知识库 + 定时清理。"""
    await init_db()
    logger.info("数据库就绪：%s", settings.db_path)

    # 应用运行时设置覆盖（DB > .env），密钥等改动即时生效
    from app.services.app_settings import load_overrides
    await load_overrides()
    logger.info("上传目录：%s", settings.upload_dir)
    logger.info("结果目录：%s", settings.result_dir)
    if settings.has_credentials:
        logger.info("火山引擎密钥已配置，将调真实 API")
    else:
        logger.warning("火山引擎密钥未配置，即梦生成会直接失败")

    # 初始化 RAG 知识库
    from app.services.rag import init_knowledge_base, is_available
    await init_knowledge_base()
    if is_available():
        logger.info("RAG 知识库已就绪")
    else:
        logger.warning("RAG 未启用（pip install chromadb sentence-transformers 后生效）")

    # 启动定时清理后台任务
    cleanup_task = asyncio.create_task(_cleanup_old_files())
    logger.info("定时清理任务已启动（每 24 小时清理 7 天前文件）")

    yield

    # 关闭时取消定时任务
    cleanup_task.cancel()


app = FastAPI(title="Photo AI Backend", version="0.1.0", lifespan=lifespan)

# CORS：允许前端跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── 请求耗时监控中间件 ───────────────────────────────────
@app.middleware("http")
async def monitor_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000

    _request_stats["total"] += 1
    _request_stats["total_time_ms"] += duration_ms
    if response.status_code >= 400:
        _request_stats["errors"] += 1
    if duration_ms > 5000:
        _request_stats["slow_requests"] += 1
        logger.warning("慢请求 %.0fms %s %s", duration_ms, request.method, request.url.path)

    return response


# 注册路由
app.include_router(tasks.router)
app.include_router(uploads.router)
app.include_router(sessions.router)
app.include_router(ws.router)
app.include_router(styles.router)
app.include_router(settings_api.router)

# 静态文件：结果图片
app.mount("/api/results", StaticFiles(directory=str(settings.result_dir)), name="results")


@app.get("/api/health")
async def health():
    from app.services.rag import is_available as rag_available
    return {
        "status": "ok",
        "has_credentials": settings.has_credentials,
        "has_ark_credentials": settings.has_ark_credentials,
        "has_dashscope_credentials": settings.has_dashscope_credentials,
        "has_qwen_llm_credentials": settings.has_qwen_llm_credentials,
        "llm_provider": settings.llm_provider,
        "image_provider": settings.image_provider,
        "rag_enabled": rag_available(),
        "doubao_model": settings.doubao_model,
        "qwen_text_model": settings.qwen_text_model,
        "jimeng_api_base": settings.jimeng_api_base,
        "jimeng_max_concurrency": settings.jimeng_max_concurrency,
        "main_image_strength": settings.main_image_strength,
    }


@app.get("/api/metrics")
async def metrics():
    """监控指标：任务统计 + 请求统计。"""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status")
        rows = await cursor.fetchall()
    finally:
        await db.close()

    task_stats = {r["status"]: r["cnt"] for r in rows}
    total_tasks = sum(task_stats.values())
    done = task_stats.get("done", 0)
    failed = task_stats.get("failed", 0)
    success_rate = (done / total_tasks * 100) if total_tasks > 0 else 0

    total_req = _request_stats["total"]
    avg_ms = (_request_stats["total_time_ms"] / total_req) if total_req > 0 else 0

    return {
        "tasks": {
            "total": total_tasks,
            "done": done,
            "failed": failed,
            "in_progress": total_tasks - done - failed,
            "success_rate": f"{success_rate:.1f}%",
        },
        "requests": {
            "total": total_req,
            "errors": _request_stats["errors"],
            "avg_time_ms": f"{avg_ms:.0f}",
            "slow_requests (>5s)": _request_stats["slow_requests"],
        },
        "node_timing": get_node_stats(),
    }


# ─── P2：知识库管理 API ────────────────────────────────────

@app.get("/api/kb/stats")
async def kb_stats():
    """查看知识库统计信息：文件数、chunk 数、模型、分类分布、上次构建时间。"""
    from app.services.rag import get_kb_stats
    return get_kb_stats()


@app.post("/api/kb/rebuild")
async def kb_rebuild():
    """强制重建知识库索引（新增/修改 kb 文件后调用）。

    流程：清空旧向量 → 重新切分 → 重新 embedding → 重建 BM25 索引 → 清空检索缓存。
    """
    from app.services.rag import rebuild_knowledge_base, clear_cache
    clear_cache()
    stats = await rebuild_knowledge_base()
    logger.info("知识库已通过 API 重建：%s", stats)
    return {"status": "ok", "stats": stats}
