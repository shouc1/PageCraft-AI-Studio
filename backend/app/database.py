"""SQLite 异步数据库连接。"""

import aiosqlite
from app.config import settings

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    user_prompt TEXT NOT NULL,
    workflow TEXT NOT NULL DEFAULT 'image2image',
    status TEXT NOT NULL DEFAULT 'pending',
    progress INTEGER NOT NULL DEFAULT 0,
    input_image TEXT,
    mask_image TEXT,  -- 已废弃（inpaint 功能已删除），保留列兼容历史数据，新任务恒为 NULL
    result_image TEXT,
    expanded_prompt TEXT,
    params_json TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

CREATE_EVENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS task_events (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    message TEXT NOT NULL,
    progress INTEGER NOT NULL,
    metadata_json TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
);
"""

# 商品会话表（需求 v2 §6.4）：三个模块共享的资产容器
CREATE_SESSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS product_sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    images TEXT NOT NULL DEFAULT '[]',
    selling_points TEXT NOT NULL DEFAULT '[]',
    style TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# 运行时设置覆盖表（方案 B：DB 覆盖 > .env，删除记录 = 回落 .env 默认值）
CREATE_APP_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


async def _ensure_column(db: aiosqlite.Connection, table: str, column: str, definition: str):
    cursor = await db.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    existing = {row["name"] for row in rows}
    if column not in existing:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(settings.db_path)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    """启动时调用，建表 + 开启 WAL 模式。"""
    db = await get_db()
    try:
        await db.execute("PRAGMA journal_mode=WAL")     # WAL 模式：读写不互斥
        await db.execute("PRAGMA busy_timeout=5000")    # 写锁冲突时等待 5 秒
        await db.execute(CREATE_TABLE_SQL)
        await _ensure_column(db, "tasks", "mask_image", "TEXT")
        # 需求 v2：任务挂载到商品会话 + 子任务聚合
        await _ensure_column(db, "tasks", "session_id", "TEXT")
        await _ensure_column(db, "tasks", "parent_task_id", "TEXT")
        await _ensure_column(db, "tasks", "kind", "TEXT DEFAULT 'single'")
        await _ensure_column(db, "tasks", "image_index", "INTEGER")
        await _ensure_column(db, "tasks", "strength", "REAL")
        await _ensure_column(db, "tasks", "size", "TEXT")
        await _ensure_column(db, "tasks", "consistency_json", "TEXT")
        await _ensure_column(db, "tasks", "sku", "TEXT")
        await db.execute(CREATE_EVENTS_TABLE_SQL)
        await db.execute(CREATE_SESSIONS_TABLE_SQL)
        await db.execute(CREATE_APP_SETTINGS_TABLE_SQL)
        await db.commit()
    finally:
        await db.close()
