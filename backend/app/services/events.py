"""Persistent task timeline events."""

import json
import uuid
from datetime import datetime, timezone
from app.database import get_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def add_task_event(
    task_id: str,
    stage: str,
    message: str,
    progress: int,
    metadata: dict | None = None,
) -> None:
    """Append a task timeline event."""
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO task_events
               (id, task_id, stage, message, progress, metadata_json, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                task_id,
                stage,
                message,
                progress,
                json.dumps(metadata or {}, ensure_ascii=False),
                _now_iso(),
            ),
        )
        await db.commit()
    finally:
        await db.close()


async def list_task_events(task_id: str) -> list[dict]:
    """Return task events in insertion order."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT id, task_id, stage, message, progress, metadata_json, timestamp
               FROM task_events WHERE task_id = ?
               ORDER BY timestamp ASC, id ASC""",
            (task_id,),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    events = []
    for row in rows:
        item = dict(row)
        raw_metadata = item.pop("metadata_json") or "{}"
        try:
            item["metadata"] = json.loads(raw_metadata)
        except json.JSONDecodeError:
            item["metadata"] = {}
        events.append(item)
    return events
