"""任务 CRUD 路由。"""

import json
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.database import get_db
from app.config import settings
from app.models.task import TaskCreate, TaskResponse, TaskListItem, ConfirmBody, TaskEventResponse, now_iso
from app.services.workflows import select_workflow
from app.logger import logger

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse)
async def create_task(body: TaskCreate):
    """创建任务，返回任务详情。任务异步执行，前端连 WebSocket 获取进度。

    支持挂载到商品会话（session_id）、指定任务类型（kind）、i2i 重绘强度（strength）
    与生图尺寸（size）；多图参考取第一张作为 i2i 主体，其余经会话 images 融合。
    """
    task_id = str(uuid.uuid4())
    now = now_iso()
    input_image = body.input_image or (body.images[0] if body.images else None)
    try:
        workflow = select_workflow(body.workflow, input_image)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    kind = body.kind or "single"
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO tasks
               (id, user_prompt, workflow, status, progress, input_image,
                session_id, kind, strength, size, created_at, updated_at)
               VALUES (?, ?, ?, 'pending', 0, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_id,
                body.user_prompt,
                workflow,
                input_image,
                body.session_id,
                kind,
                body.strength,
                body.size,
                now,
                now,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    from app.services.events import add_task_event
    await add_task_event(
        task_id,
        "pending",
        "任务已创建",
        0,
        {"requested_workflow": body.workflow or "auto", "selected_workflow": workflow},
    )

    # 异步启动任务执行器（导入放这里避免循环依赖）
    from app.services.task_runner import start_task
    await start_task(task_id)

    return TaskResponse(
        id=task_id,
        user_prompt=body.user_prompt,
        workflow=workflow,
        status="pending",
        progress=0,
        input_image=input_image,
        session_id=body.session_id,
        kind=kind,
        created_at=now,
        updated_at=now,
    )


@router.get("", response_model=list[TaskListItem])
async def list_tasks(limit: int = 20):
    """获取任务列表。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT id, user_prompt, workflow, status, progress, result_image,
                      session_id, kind, created_at
               FROM tasks ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    return [TaskListItem(**dict(r)) for r in rows]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """查询单个任务详情。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT id, user_prompt, workflow, status, progress,
                      input_image, result_image, expanded_prompt, error_message,
                      session_id, parent_task_id, kind, image_index, sku, consistency_json,
                      created_at, updated_at
               FROM tasks WHERE id = ?""",
            (task_id,),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    data = dict(row)
    # 解析一致性校验结果 JSON
    raw_consistency = data.pop("consistency_json") or None
    if raw_consistency:
        try:
            data["consistency"] = json.loads(raw_consistency)
        except json.JSONDecodeError:
            data["consistency"] = None

    return TaskResponse(**data)


@router.get("/{task_id}/events", response_model=list[TaskEventResponse])
async def get_task_events(task_id: str):
    """查询任务时间线事件。"""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
    finally:
        await db.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    from app.services.events import list_task_events
    return await list_task_events(task_id)


@router.post("/{task_id}/confirm")
async def confirm_task(task_id: str, body: ConfirmBody):
    """用户确认或修改 prompt 后，继续执行生成阶段。

    仅当任务状态为 awaiting_confirmation 时允许调用。
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT status, expanded_prompt FROM tasks WHERE id = ?",
            (task_id,),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if row["status"] != "awaiting_confirmation":
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 {row['status']} 不可确认，需为 awaiting_confirmation",
        )

    # 用户未修改时复用原 prompt
    final_prompt = body.prompt.strip() or row["expanded_prompt"] or ""

    from app.services.task_runner import resume_task
    await resume_task(task_id, final_prompt)

    return {"status": "ok", "task_id": task_id, "prompt": final_prompt}


@router.post("/{task_id}/regenerate")
async def regenerate_task(task_id: str):
    """单张重生成（需求 v2 §6.1/6.3）：重新运行该任务，不整组重来。

    批量场景下子任务独立重生成；父任务进度会自动重新聚合。
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT user_prompt FROM tasks WHERE id = ?", (task_id,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # 重置任务并重新启动生成
    db = await get_db()
    try:
        await db.execute(
            """UPDATE tasks SET status = 'pending', progress = 0,
                   error_message = NULL, result_image = NULL, consistency_json = NULL,
                   updated_at = ?
               WHERE id = ?""",
            (now_iso(), task_id),
        )
        await db.commit()
    finally:
        await db.close()

    from app.services.task_runner import start_direct_generation
    await start_direct_generation(task_id, row["user_prompt"])

    logger.info("任务重生成已启动 %s", task_id)
    return {"status": "ok", "task_id": task_id}


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """删除任务及其关联的上传原图和生成结果图片。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT input_image, result_image FROM tasks WHERE id = ?",
            (task_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Task not found")

        # 删除关联的物理文件
        for field in ("input_image", "result_image"):
            filename = row[field]
            if not filename:
                continue
            # result_image 存的是 /api/results/xxx.png 格式
            if filename.startswith("/api/"):
                filename = filename.split("/")[-1]
                file_path = settings.result_dir / filename
            else:
                file_path = settings.upload_dir / filename
            if file_path.exists():
                file_path.unlink()
                logger.info("已删除文件 %s", file_path)

        await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await db.execute("DELETE FROM task_events WHERE task_id = ?", (task_id,))
        await db.commit()
    finally:
        await db.close()

    logger.info("任务已删除 %s", task_id)
    return {"status": "ok", "task_id": task_id}


@router.get("/{task_id}/download")
async def download_image(task_id: str):
    """下载任务的生成结果图片。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT result_image FROM tasks WHERE id = ?",
            (task_id,),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    result_image = row["result_image"]
    if not result_image:
        raise HTTPException(status_code=404, detail="该任务没有生成结果图片")

    # 解析文件名
    if result_image.startswith("/api/"):
        filename = result_image.split("/")[-1]
    else:
        filename = result_image

    file_path = settings.result_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="图片文件不存在")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="image/png",
    )
