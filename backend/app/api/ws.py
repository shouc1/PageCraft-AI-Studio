"""WebSocket 路由，推送任务进度。"""

import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.database import get_db

router = APIRouter(prefix="/ws")


class ConnectionManager:
    """管理每个任务的 WebSocket 连接。"""

    def __init__(self):
        # task_id -> set[WebSocket]
        self._connections: dict[str, set[WebSocket]] = {}

    def connect(self, task_id: str, ws: WebSocket):
        if task_id not in self._connections:
            self._connections[task_id] = set()
        self._connections[task_id].add(ws)

    def disconnect(self, task_id: str, ws: WebSocket):
        if task_id in self._connections:
            self._connections[task_id].discard(ws)
            if not self._connections[task_id]:
                del self._connections[task_id]

    async def broadcast(self, task_id: str, message: dict):
        """给某个任务的所有连接推送消息。"""
        if task_id not in self._connections:
            return
        dead = []
        for ws in self._connections[task_id]:
            try:
                await ws.send_text(json.dumps(message, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(task_id, ws)


manager = ConnectionManager()


@router.websocket("/tasks/{task_id}")
async def ws_task_progress(websocket: WebSocket, task_id: str):
    """WebSocket 端点：/ws/tasks/{task_id}，推送任务进度。

    消息格式：
    {
        "type": "status",
        "task_id": "xxx",
        "status": "planning",
        "progress": 18,
        "message": "正在扩展生成 prompt..."
    }
    """
    await websocket.accept()
    manager.connect(task_id, websocket)

    # 连接时先推一次当前状态
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT status, progress, result_image FROM tasks WHERE id = ?",
            (task_id,),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()

    if row:
        await websocket.send_text(json.dumps({
            "type": "status",
            "task_id": task_id,
            "status": row["status"],
            "progress": row["progress"],
            "message": f"当前状态：{row['status']}",
        }, ensure_ascii=False))

    try:
        # 保持连接，等待服务端推送
        while True:
            await asyncio.sleep(30)  # 心跳间隔
            await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        manager.disconnect(task_id, websocket)
    finally:
        manager.disconnect(task_id, websocket)
