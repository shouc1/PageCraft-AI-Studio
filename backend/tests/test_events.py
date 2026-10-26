import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path


class TaskEventsTest(unittest.TestCase):
    def test_add_and_list_task_events(self):
        async def run():
            with tempfile.TemporaryDirectory() as tmp:
                # 保存真实模块，finally 还原，避免污染同进程后续测试
                saved = {
                    name: sys.modules.get(name)
                    for name in ("app.config", "app.database", "app.services.events")
                }
                try:
                    settings = types.SimpleNamespace(db_path=Path(tmp) / "test.db")
                    fake_config = types.ModuleType("app.config")
                    fake_config.settings = settings
                    sys.modules["app.config"] = fake_config
                    sys.modules.pop("app.database", None)
                    sys.modules.pop("app.services.events", None)

                    from app.database import get_db, init_db
                    from app.services.events import add_task_event, list_task_events

                    await init_db()
                    db = await get_db()
                    try:
                        await db.execute(
                            """INSERT INTO tasks
                               (id, user_prompt, workflow, status, progress, created_at, updated_at)
                               VALUES ('task_1', 'test', 'text2image', 'pending', 0, 'now', 'now')"""
                        )
                        await db.commit()
                    finally:
                        await db.close()

                    await add_task_event(
                        "task_1",
                        "planning",
                        "商品分析中",
                        8,
                        {"node": "analyze"},
                    )
                    await add_task_event("task_1", "done", "完成", 100)

                    events = await list_task_events("task_1")
                    self.assertEqual([event["stage"] for event in events], ["planning", "done"])
                    self.assertEqual(events[0]["metadata"]["node"], "analyze")
                finally:
                    for name, mod in saved.items():
                        if mod is not None:
                            sys.modules[name] = mod
                        else:
                            sys.modules.pop(name, None)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
