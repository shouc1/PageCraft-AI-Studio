"""任务执行器：编排 LLM + 即梦 + WebSocket 推送。

流程：pending → planning（三专家流水线）→ awaiting_confirmation（等用户确认/修改 prompt）
      → generating → saving → done
失败：任意阶段 → failed

确认环节：planning 完成后任务暂停，等待前端 POST /api/tasks/{id}/confirm
         传入（可能被用户修改过的）prompt，再继续 generating 阶段。
"""

import asyncio
import json
from app.database import get_db
from app.config import settings
from app.models.task import now_iso
from app.services.llm import expand_prompt
from app.services import qwen as qwen_service
from app.services.jimeng import generate as jimeng_generate
from app.services.consistency import check_consistency
from app.api.ws import manager
from app.logger import logger

# planning 阶段三专家 + RAG 对应的进度
STEP_PROGRESS = {
    "analyzing": 8,
    "retrieving": 12,
    "designing": 16,
    "reviewing": 20,
}

# 各阶段默认进度
PROGRESS_AWAITING = 25
PROGRESS_GENERATING = 60
PROGRESS_SAVING = 92
PROGRESS_DONE = 100

# LLM planning 并发：避免同时压豆包（固定上限）
_planning_semaphore = asyncio.Semaphore(3)

# 即梦生图并发排队（需求 v2 §9 决策4）：按火山控制台配额配置，默认 1。
# 一图一子任务统一过队列；配额升级只改配置不改代码。
_generating_semaphore = asyncio.Semaphore(max(1, settings.jimeng_max_concurrency))


async def _update_task(
    task_id: str,
    *,
    status: str | None = None,
    progress: int | None = None,
    message: str = "",
    metadata: dict | None = None,
    **fields,
):
    """更新数据库里的任务字段，并广播进度。"""
    if status:
        fields["status"] = status
    if progress is not None:
        fields["progress"] = progress
    fields["updated_at"] = now_iso()

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [task_id]

    db = await get_db()
    try:
        await db.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
        await db.commit()
    finally:
        await db.close()

    # 广播到 WebSocket
    final_status = status or fields.get("status", "")
    final_progress = progress if progress is not None else fields.get("progress", 0)
    if not message:
        message_map = {
            "planning": "语言模型正在扩写生成 prompt...",
            "awaiting_confirmation": "请确认或修改生成的 prompt",
            "generating": "AI 正在生成图像...",
            "saving": "正在保存生成结果...",
            "done": "生成完成！",
            "failed": f"生成失败：{fields.get('error_message', '')}",
        }
        message = message_map.get(final_status, "")

    await manager.broadcast(task_id, {
        "type": "status",
        "task_id": task_id,
        "status": final_status,
        "progress": final_progress,
        "message": message,
    })

    from app.services.events import add_task_event
    await add_task_event(task_id, final_status, message, final_progress, metadata)


async def start_task(task_id: str):
    """异步启动任务执行（不阻塞请求）。"""
    asyncio.create_task(_run_planning(task_id))


async def _run_planning(task_id: str):
    """阶段 1：planning（三专家流水线）→ awaiting_confirmation。"""
    try:
        # 并发控制：等待空闲槽位
        async with _planning_semaphore:
            logger.info("任务 %s 开始 planning（并发槽位已获取）", task_id)
            db = await get_db()
            try:
                cursor = await db.execute(
                    "SELECT user_prompt, workflow, input_image FROM tasks WHERE id = ?",
                    (task_id,),
                )
                row = await cursor.fetchone()
            finally:
                await db.close()

            if row is None:
                return

            user_prompt = row["user_prompt"]

            # 三专家流水线的细粒度进度回调
            async def on_progress(step: str, message: str, metadata: dict | None = None):
                progress = STEP_PROGRESS.get(step, 15)
                await _update_task(
                    task_id,
                    status="planning",
                    progress=progress,
                    message=message,
                    metadata=metadata,
                )

            # 判断是否图生图场景
            is_i2i = bool(row["input_image"]) and row["workflow"] != "text2image"

            expanded = await expand_prompt(user_prompt, on_progress=on_progress, is_image_to_image=is_i2i)

        # planning 完成 → 进入等待确认（已释放并发槽位）
        await _update_task(
            task_id,
            status="awaiting_confirmation",
            progress=PROGRESS_AWAITING,
            message="请确认或修改生成的 prompt",
            expanded_prompt=expanded,
        )

    except Exception as e:
        logger.exception("planning 阶段失败，task_id=%s", task_id)
        error_message = str(e)
        if e.__class__.__name__ == "RetryError":
            cause = getattr(e, "last_attempt", None)
            if cause:
                try:
                    error_message = f"LLM 服务连接失败：{cause.exception()}"
                except Exception:
                    error_message = "LLM 服务连接失败，请检查 ARK_API_KEY、DOUBAO_MODEL 和网络"
        await _update_task(
            task_id,
            status="failed",
            progress=0,
            error_message=error_message,
        )


async def resume_task(task_id: str, confirmed_prompt: str):
    """用户确认 prompt 后调用，继续执行 generating → saving → done。"""
    asyncio.create_task(_run_generation(task_id, confirmed_prompt))


async def _collect_input_images(input_image: str | None, session_id: str | None) -> list[str]:
    """收集参考图文件名列表：任务 input_image + 会话 images（多参考图融合）。"""
    images: list[str] = []
    if input_image:
        images.append(input_image)
    if session_id:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT images FROM product_sessions WHERE id = ?", (session_id,)
            )
            row = await cursor.fetchone()
        finally:
            await db.close()
        if row:
            try:
                session_images = json.loads(row["images"] or "[]")
            except json.JSONDecodeError:
                session_images = []
            for img in session_images:
                if img and img not in images:
                    images.append(img)
    return images


async def _update_parent_progress(parent_task_id: str):
    """根据子任务状态聚合父任务进度（第 N/M 张）。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done,
                      SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed
               FROM tasks WHERE parent_task_id = ?""",
            (parent_task_id,),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()

    total = row["total"] or 0
    done = row["done"] or 0
    failed = row["failed"] or 0
    if total == 0:
        return

    if done + failed >= total:
        # 全部子任务完成（含失败）
        status = "done" if failed == 0 else "failed"
        progress = PROGRESS_DONE
        message = "整组生成完成" if failed == 0 else f"生成完成（{failed} 张失败）"
    else:
        status = "generating"
        progress = PROGRESS_GENERATING + int((done / total) * (PROGRESS_DONE - PROGRESS_GENERATING))
        message = f"第 {done + 1}/{total} 张生成中"

    await _update_task(parent_task_id, status=status, progress=progress, message=message)


async def _run_generation(task_id: str, prompt: str):
    """阶段 2~4：generating → saving → done（含一致性校验 + 父任务进度聚合）。"""
    try:
        db = await get_db()
        try:
            cursor = await db.execute(
                """SELECT workflow, input_image, strength, size,
                          session_id, parent_task_id
                   FROM tasks WHERE id = ?""",
                (task_id,),
            )
            row = await cursor.fetchone()
        finally:
            await db.close()

        if row is None:
            return

        workflow = row["workflow"]
        input_image = row["input_image"]
        strength = row["strength"]
        size = row["size"]
        session_id = row["session_id"]
        parent_task_id = row["parent_task_id"]

        # ── 阶段 2：generating（即梦生图，统一过并发队列）──
        await _update_task(
            task_id,
            status="generating",
            progress=PROGRESS_GENERATING,
            message="AI 正在生成图像...",
            expanded_prompt=prompt,
        )

        # 收集多参考图（会话多图融合，需求 v2 §5）
        input_images = await _collect_input_images(input_image, session_id)

        async with _generating_semaphore:
            logger.info("任务 %s 开始 generating（并发槽位已获取，厂商=%s）", task_id, settings.image_provider)
            # 全局厂商选择：设置页切换，调用时读取单例即时生效
            if settings.image_provider == "qwen":
                result = await qwen_service.generate(
                    workflow, prompt, input_images, strength, size
                )
            else:
                result = await jimeng_generate(
                    workflow, prompt, input_images, strength, size
                )

        if isinstance(result, tuple):
            result_path, provider_metadata = result
        else:
            result_path = result
            provider_metadata = {}

        # ── 一致性校验（需求 v2 §5.2）：生成图 vs 原图像似度──
        # 校验失败不阻断交付：图照常展示，错误记录到 consistency.warning
        consistency = None
        source_images = input_images or ([input_image] if input_image else [])
        if source_images:
            source_file = source_images[0]
            source_path = None
            for directory in (settings.upload_dir, settings.result_dir):
                candidate = directory / source_file
                if candidate.exists():
                    source_path = candidate
                    break
            if source_path:
                try:
                    consistency = await check_consistency(source_path, result_path)
                except Exception as ce:
                    logger.warning(
                        "一致性校验失败（不影响结果展示），task_id=%s: %s", task_id, ce
                    )
                    consistency = {
                        "available": False,
                        "similarity": None,
                        "distortion_suspected": None,
                        "method": "error",
                        "warning": f"一致性校验出错：{ce}",
                    }

        # ── 阶段 3：saving（保存结果）──
        await _update_task(
            task_id,
            status="saving",
            progress=PROGRESS_SAVING,
            message="正在保存生成结果...",
            metadata=provider_metadata,
        )

        result_filename = result_path.name
        result_url = f"/api/results/{result_filename}"

        # ── 阶段 4：done ──
        await _update_task(
            task_id,
            status="done",
            progress=PROGRESS_DONE,
            message="生成完成！",
            result_image=result_url,
            consistency_json=json.dumps(consistency, ensure_ascii=False) if consistency else None,
        )

        # 子任务完成后聚合父任务进度（需求 v2 §6.3）
        if parent_task_id:
            await _update_parent_progress(parent_task_id)

    except Exception as e:
        logger.exception("generating 阶段失败，task_id=%s", task_id)
        await _update_task(
            task_id,
            status="failed",
            progress=0,
            error_message=str(e),
        )
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT parent_task_id FROM tasks WHERE id = ?", (task_id,)
            )
            row = await cursor.fetchone()
        finally:
            await db.close()
        if row and row["parent_task_id"]:
            await _update_parent_progress(row["parent_task_id"])


async def start_direct_generation(task_id: str, prompt: str):
    """直接生成（跳过 planning / 确认）：用于已确认 prompt 的单张重生成。"""
    asyncio.create_task(_run_generation(task_id, prompt))


async def start_batch_planning(task_id: str):
    """批量子任务入口：planning（三专家扩写）→ 自动续跑 generating（跳过人工确认）。"""
    asyncio.create_task(_run_batch_planning(task_id))


async def _run_batch_planning(task_id: str):
    """批量子任务的三专家扩写 + 自动进入生成阶段。

    与单任务流程的差异：planning 完成后不进 awaiting_confirmation，
    直接以扩写结果调用 _run_generation（批量场景无需逐张人工确认）。
    """
    try:
        async with _planning_semaphore:
            logger.info("批量子任务 %s 开始 planning（并发槽位已获取）", task_id)
            db = await get_db()
            try:
                cursor = await db.execute(
                    "SELECT user_prompt, workflow, input_image FROM tasks WHERE id = ?",
                    (task_id,),
                )
                row = await cursor.fetchone()
            finally:
                await db.close()

            if row is None:
                return

            async def on_progress(step: str, message: str, metadata: dict | None = None):
                progress = STEP_PROGRESS.get(step, 15)
                await _update_task(
                    task_id,
                    status="planning",
                    progress=progress,
                    message=message,
                    metadata=metadata,
                )

            is_i2i = bool(row["input_image"]) and row["workflow"] != "text2image"
            expanded = await expand_prompt(
                row["user_prompt"], on_progress=on_progress, is_image_to_image=is_i2i
            )

        # 扩写完成 → 直接进入生成（生成阶段内部自带异常处理与父任务进度聚合）
        await _run_generation(task_id, expanded)

    except Exception as e:
        logger.exception("批量子任务 planning 阶段失败，task_id=%s", task_id)
        error_message = str(e)
        if e.__class__.__name__ == "RetryError":
            cause = getattr(e, "last_attempt", None)
            if cause:
                try:
                    error_message = f"LLM 服务连接失败：{cause.exception()}"
                except Exception:
                    error_message = "LLM 服务连接失败，请检查语言模型厂商凭证与网络"
        await _update_task(
            task_id,
            status="failed",
            progress=0,
            error_message=f"prompt 扩写失败：{error_message}",
        )
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT parent_task_id FROM tasks WHERE id = ?", (task_id,)
            )
            row = await cursor.fetchone()
        finally:
            await db.close()
        if row and row["parent_task_id"]:
            await _update_parent_progress(row["parent_task_id"])
