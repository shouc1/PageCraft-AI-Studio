"""商品会话路由（需求 v2 §6.4）。

商品会话是主图 / 详情页 / 文案三个模块共享的资产容器：
类目、卖点、风格、商品图。此处提供会话 CRUD + 类目识别 + 卖点提取 +
主图 / 详情页批量生成入口（风格推荐见 /api/styles，styles.py）。
"""

import json
import uuid
from fastapi import APIRouter, HTTPException, Query
from app.database import get_db
from app.config import settings
from app.models.task import (
    now_iso,
    SessionCreate,
    SessionUpdate,
    SessionResponse,
    SellingPoint,
    CategoryResult,
    SellingPointsResult,
    GenerateImagesRequest,
    HintRequest,
    DetailSlot,
    DetailPlanResult,
    CopywritingPlan,
    CopywritingResult,
)
from app.logger import logger

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

SESSION_COLUMNS = "id, name, category, images, selling_points, style, status, created_at, updated_at"


def _row_to_session(row) -> SessionResponse:
    """数据库行 → SessionResponse（解析 images / selling_points JSON）。"""
    d = dict(row)
    try:
        d["images"] = json.loads(d.get("images") or "[]")
    except json.JSONDecodeError:
        d["images"] = []
    try:
        raw_points = json.loads(d.get("selling_points") or "[]")
        d["selling_points"] = [SellingPoint(**p) for p in raw_points]
    except (json.JSONDecodeError, TypeError):
        d["selling_points"] = []
    return SessionResponse(**d)


async def _get_session(session_id: str):
    """加载会话，不存在则抛 404。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            f"SELECT {SESSION_COLUMNS} FROM product_sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    if row is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return row


# ─── 会话 CRUD ────────────────────────────────────────────

@router.post("", response_model=SessionResponse)
async def create_session(body: SessionCreate):
    """创建商品会话（上传 1~6 张商品图后建立资产容器）。"""
    session_id = str(uuid.uuid4())
    now = now_iso()
    if not 0 <= len(body.images) <= 6:
        raise HTTPException(status_code=400, detail="商品图数量需在 1~6 张之间")

    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO product_sessions
               (id, name, category, images, selling_points, style, status, created_at, updated_at)
               VALUES (?, ?, '', ?, '[]', '', 'draft', ?, ?)""",
            (
                session_id,
                body.name or "",
                json.dumps(body.images, ensure_ascii=False),
                now,
                now,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    logger.info("会话已创建 %s（图片 %d 张）", session_id, len(body.images))
    return _row_to_session(await _get_session(session_id))


@router.get("", response_model=list[SessionResponse])
async def list_sessions(limit: int = Query(50, ge=1, le=200)):
    """会话列表（按更新时间倒序）。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            f"SELECT {SESSION_COLUMNS} FROM product_sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [_row_to_session(r) for r in rows]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """会话详情。"""
    return _row_to_session(await _get_session(session_id))


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(session_id: str, body: SessionUpdate):
    """更新会话资产：名称 / 类目 / 卖点 / 风格 / 商品图（可人工修正）。"""
    await _get_session(session_id)

    fields = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.category is not None:
        fields["category"] = body.category
    if body.selling_points is not None:
        fields["selling_points"] = json.dumps(
            [p.model_dump() for p in body.selling_points], ensure_ascii=False
        )
    if body.style is not None:
        fields["style"] = body.style
    if body.images is not None:
        if not 0 <= len(body.images) <= 6:
            raise HTTPException(status_code=400, detail="商品图数量需在 1~6 张之间")
        fields["images"] = json.dumps(body.images, ensure_ascii=False)
    fields["updated_at"] = now_iso()

    if not fields:
        return _row_to_session(await _get_session(session_id))

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    db = await get_db()
    try:
        await db.execute(
            f"UPDATE product_sessions SET {set_clause} WHERE id = ?",
            list(fields.values()) + [session_id],
        )
        await db.commit()
    finally:
        await db.close()

    logger.info("会话已更新 %s：%s", session_id, ", ".join(fields.keys()))
    return _row_to_session(await _get_session(session_id))


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """删除会话（关联任务保留，仅移除资产容器）。"""
    await _get_session(session_id)
    db = await get_db()
    try:
        await db.execute("DELETE FROM product_sessions WHERE id = ?", (session_id,))
        await db.commit()
    finally:
        await db.close()
    logger.info("会话已删除 %s", session_id)
    return {"status": "ok", "session_id": session_id}


# ─── 类目识别（F-M1）────────────────────────────────────

@router.post("/{session_id}/categorize", response_model=CategoryResult)
async def categorize_session(session_id: str, body: HintRequest):
    """识别商品类目（基于用户描述 + 5 类目知识库）。低置信度时返回候选供确认。"""
    session = await _get_session(session_id)
    from app.services.llm import categorize_product

    hint = body.user_hint or session["name"] or ""
    result = await categorize_product(hint)

    # 高置信度时自动写回会话的 category
    confidence = result.get("confidence", 0.0)
    need_confirm = confidence < 0.7 or not result.get("category")
    if not need_confirm and result.get("category"):
        db = await get_db()
        try:
            await db.execute(
                "UPDATE product_sessions SET category = ?, updated_at = ? WHERE id = ?",
                (result["category"], now_iso(), session_id),
            )
            await db.commit()
        finally:
            await db.close()

    return CategoryResult(
        category=result.get("category", ""),
        confidence=confidence,
        candidates=result.get("candidates", []),
        need_confirm=need_confirm,
    )


# ─── 卖点提取（F-M2）────────────────────────────────────

@router.post("/{session_id}/selling-points", response_model=SellingPointsResult)
async def extract_session_selling_points(session_id: str, body: HintRequest):
    """基于类目 + 用户提示词提炼结构化卖点（RAG 卖点视觉化词典辅助）。"""
    session = await _get_session(session_id)
    from app.services.llm import extract_selling_points
    from app.services.rag import retrieve_knowledge, is_available

    category = session["category"] or ""
    user_hint = body.user_hint or session["name"] or ""

    # 检索卖点视觉化词典，帮助卖点翻译成视觉化写法
    knowledge: list[str] = []
    if is_available():
        knowledge = await retrieve_knowledge(
            f"{category} {user_hint}", top_k=3, category="visual_dict"
        )

    result = await extract_selling_points(category, user_hint, knowledge)
    points = result.get("selling_points", [])

    return SellingPointsResult(category=category, selling_points=[SellingPoint(**p) for p in points])


# ─── 批量生图内部编排（主图 / 详情页共用）────────────────

async def _start_generation_batch(
    session,
    prompts: list[str],
    kind: str,
    size: str,
    parent_kind: str,
    workflow: str | None = None,
    skus: list[str] | None = None,
) -> dict:
    """创建父任务 + N 子任务（一张图 = 一个子任务）并异步启动生成。

    支持 SKU 变体批量（§6.2）：skus 非空时，为每个变体 × 每张图创建子任务，
    子任务标记 sku，父任务聚合全部子任务进度。
    """
    session_id = session["id"]
    session_images = json.loads(session["images"] or "[]")
    work = workflow or ("image2image" if session_images else "text2image")
    strength = settings.main_image_strength if work == "image2image" else None

    parent_id = str(uuid.uuid4())
    now = now_iso()

    # 变体任务清单：(sku, prompt, 同变体内图片序号)
    effective_skus = [s for s in (skus or []) if s and s.strip()] or [None]
    jobs = []
    for sku in effective_skus:
        for i, prompt in enumerate(prompts):
            jobs.append((sku, prompt, i))

    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO tasks
               (id, user_prompt, workflow, status, progress, session_id, kind, created_at, updated_at)
               VALUES (?, ?, ?, 'planning', 0, ?, ?, ?, ?)""",
            (parent_id, "", work, session_id, parent_kind, now, now),
        )
        subtask_ids = []
        for sku, prompt, image_index in jobs:
            subtask_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO tasks
                   (id, user_prompt, workflow, status, progress, session_id,
                    parent_task_id, kind, image_index, sku, strength, size, created_at, updated_at)
                   VALUES (?, ?, ?, 'pending', 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    subtask_id,
                    prompt,
                    work,
                    session_id,
                    parent_id,
                    kind,
                    image_index,
                    sku,
                    strength,
                    size,
                    now,
                    now,
                ),
            )
            subtask_ids.append(subtask_id)
        await db.commit()
    finally:
        await db.close()

    # 批量子任务先过三专家流水线扩写 prompt（不进人工确认态，扩写后自动生图）
    from app.services.task_runner import start_batch_planning
    for subtask_id in subtask_ids:
        await start_batch_planning(subtask_id)

    return {
        "status": "ok",
        "parent_task_id": parent_id,
        "subtask_ids": subtask_ids,
        "count": len(subtask_ids),
    }


# ─── 主图批量生成（F-M4）────────────────────────────────

@router.post("/{session_id}/main-images")
async def generate_main_images(session_id: str, body: GenerateImagesRequest):
    """批量生成主图：创建父任务 + N 子任务（一张图 = 一个子任务）。

    每个子任务独立生成、可单张重生成，父任务聚合进度（第 N/M 张）。
    """
    session = await _get_session(session_id)
    prompts = [p.strip() for p in body.prompts if p and p.strip()]
    if not prompts:
        raise HTTPException(status_code=400, detail="prompts 不能为空")

    # 目标平台决定主图尺寸（§6.5），未指定用默认主图尺寸
    from app.services.platforms import resolve_platform_size
    size = resolve_platform_size(body.platform, settings.main_image_size)
    result = await _start_generation_batch(
        session, prompts, body.kind, size, "main_cover", body.workflow, body.skus
    )
    logger.info("主图批量生成已启动：父任务 %s，%d 张", result["parent_task_id"], result["count"])
    return result


# ─── P1：详情页结构规划（F-D1）───────────────────────────

@router.get("/{session_id}/detail-plan", response_model=DetailPlanResult)
async def get_session_detail_plan(session_id: str):
    """按类目返回详情页 6 张结构模板，供用户增删/调整每张图定位。"""
    session = await _get_session(session_id)
    from app.services.detail_plan import get_detail_plan

    result = get_detail_plan(session["category"] or "")
    return DetailPlanResult(
        category=result["category"],
        slots=[DetailSlot(**s) for s in result["slots"]],
    )


# ─── P1：详情页批量生成（F-D3）───────────────────────────

@router.post("/{session_id}/detail-images")
async def generate_detail_images(session_id: str, body: GenerateImagesRequest):
    """批量生成详情页图：复用主图子任务编排，尺寸用详情页规格（750 宽）。"""
    session = await _get_session(session_id)
    prompts = [p.strip() for p in body.prompts if p and p.strip()]
    if not prompts:
        raise HTTPException(status_code=400, detail="prompts 不能为空")

    kind = body.kind or "detail_image"
    result = await _start_generation_batch(
        session, prompts, kind, settings.detail_image_size, "detail_cover", body.workflow, body.skus
    )
    logger.info("详情页批量生成已启动：父任务 %s，%d 张", result["parent_task_id"], result["count"])
    return result


# ─── P1：营销文案生成 3 方案（F-C1 / F-C2）────────────────

@router.post("/{session_id}/copywriting", response_model=CopywritingResult)
async def generate_session_copywriting(session_id: str, body: HintRequest):
    """生成 3 套营销文案方案，并对每段文案做广告法极限词硬校验。"""
    session = await _get_session(session_id)
    from app.services.llm import generate_copywriting
    from app.services.compliance import check_compliance
    from app.services.hot_calendar import get_active_hotspots

    category = session["category"] or ""
    points = json.loads(session["selling_points"] or "[]")
    user_hint = body.user_hint or session["name"] or ""

    # 静态热点日历：临近节日/节气/大促注入文案倾向（F-C3，P1）
    hotspots = get_active_hotspots()
    result = await generate_copywriting(category, points, user_hint, hotspots)

    plans = []
    for plan in result.get("plans", []):
        issues = []
        for field in ("title", "main_copy", "detail_copy"):
            check = check_compliance(plan.get(field, ""))
            for v in check["violations"]:
                issues.append(
                    {
                        "field": field,
                        "word": v["word"],
                        "suggestion": v["suggestion"],
                        "count": v["count"],
                    }
                )
        plans.append(CopywritingPlan(**plan, issues=issues))

    return CopywritingResult(category=category, plans=plans, hotspots=hotspots)