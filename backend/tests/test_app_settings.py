"""运行时设置覆盖层测试（DB 覆盖 > .env 语义）。

全部用临时数据库隔离，不触碰真实 data.db：
- patch settings.db_path 到临时文件后 init_db 建表
- 测试后还原单例字段与 db_path，避免污染其他用例
"""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

TEST_KEY = "ARK_API_KEY"
TEST_FIELD = "ark_api_key"
TEST_VALUE = "ark-test-key-1234567890"


class AppSettingsTest(unittest.TestCase):
    def setUp(self):
        from app.config import settings
        from app.services import app_settings as svc

        self.settings = settings
        self.svc = svc
        # 保存单例字段原值与 db_path，测试后还原
        self._orig_field_value = getattr(settings, TEST_FIELD)
        self._orig_db_path = settings.db_path
        self._tmp = tempfile.TemporaryDirectory()
        settings.db_path = Path(self._tmp.name) / "test.db"

    def tearDown(self):
        self.settings.db_path = self._orig_db_path
        setattr(self.settings, TEST_FIELD, self._orig_field_value)
        self._tmp.cleanup()

    def _init_db(self):
        from app.database import init_db
        asyncio.run(init_db())

    def test_update_writes_db_and_applies_immediately(self):
        self._init_db()
        overview = asyncio.run(self.svc.update_settings({TEST_KEY: TEST_VALUE}))

        # 单例立即生效
        self.assertEqual(getattr(self.settings, TEST_FIELD), TEST_VALUE)
        # 覆盖标记 + 脱敏返回（首尾 4 位保留，中间打码）
        item = next(i for i in overview["settings"] if i["key"] == TEST_KEY)
        self.assertTrue(item["overridden"])
        self.assertNotIn(TEST_VALUE, item["value"])
        self.assertTrue(item["value"].startswith(TEST_VALUE[:4]))
        # 凭证就绪状态同步
        self.assertTrue(overview["has_ark_credentials"])

    def test_clear_falls_back_to_env_default(self):
        self._init_db()
        asyncio.run(self.svc.update_settings({TEST_KEY: TEST_VALUE}))
        overview = asyncio.run(self.svc.update_settings({TEST_KEY: ""}))

        # 回落 .env 出厂默认值（模块导入时的快照）
        self.assertEqual(
            getattr(self.settings, TEST_FIELD),
            self.svc._ENV_DEFAULTS[TEST_KEY],
        )
        item = next(i for i in overview["settings"] if i["key"] == TEST_KEY)
        self.assertFalse(item["overridden"])

    def test_load_overrides_applies_on_startup(self):
        self._init_db()
        asyncio.run(self.svc.update_settings({TEST_KEY: TEST_VALUE}))

        # 模拟重启：先还原为 env 默认值，再走启动加载
        setattr(self.settings, TEST_FIELD, self.svc._ENV_DEFAULTS[TEST_KEY])
        applied = asyncio.run(self.svc.load_overrides())

        self.assertGreaterEqual(applied, 1)
        self.assertEqual(getattr(self.settings, TEST_FIELD), TEST_VALUE)

    def test_unknown_key_rejected(self):
        self._init_db()
        with self.assertRaises(ValueError):
            asyncio.run(self.svc.update_settings({"NOT_A_KEY": "x"}))

    def test_mask_secret(self):
        self.assertEqual(self.svc.mask_secret(""), "")
        self.assertEqual(self.svc.mask_secret("short"), "••••")
        masked = self.svc.mask_secret("abcd12345678wxyz")
        self.assertEqual(masked, "abcd••••wxyz")


class JimengModelSettingsTest(unittest.TestCase):
    """即梦 req_key 可配置：设置覆盖 + adapters 调用时实际取值。"""

    JIMENG_KEYS = (
        ("JIMENG_T2I_MODEL", "jimeng_t2i_model"),
        ("JIMENG_I2I_MODEL", "jimeng_i2i_model"),
    )

    def setUp(self):
        from app.config import settings
        from app.services import app_settings as svc
        from app.database import init_db

        self.settings = settings
        self.svc = svc
        self._orig_fields = {f: getattr(settings, f) for _k, f in self.JIMENG_KEYS}
        self._orig_db_path = settings.db_path
        self._tmp = tempfile.TemporaryDirectory()
        settings.db_path = Path(self._tmp.name) / "test.db"
        asyncio.run(init_db())

    def tearDown(self):
        self.settings.db_path = self._orig_db_path
        for field, value in self._orig_fields.items():
            setattr(self.settings, field, value)
        self._tmp.cleanup()

    def test_t2i_override_reaches_adapters_immediately(self):
        from app.services.jimeng_adapters import build_jimeng_request

        overview = asyncio.run(
            self.svc.update_settings({"JIMENG_T2I_MODEL": "custom_t2i_key"})
        )
        item = next(i for i in overview["settings"] if i["key"] == "JIMENG_T2I_MODEL")
        self.assertTrue(item["overridden"])

        # adapters 在调用时读取 settings 单例，覆盖即时生效
        req = build_jimeng_request("text2image", "p", None, "1024x1024", None)
        self.assertEqual(req.body["req_key"], "custom_t2i_key")

    def test_i2i_override_reaches_adapters_immediately(self):
        from app.services.jimeng_adapters import build_jimeng_request

        asyncio.run(self.svc.update_settings({"JIMENG_I2I_MODEL": "custom_i2i_key"}))
        req = build_jimeng_request("image2image", "p", ["img"], "1024x1024", 0.4)
        self.assertEqual(req.body["req_key"], "custom_i2i_key")

    def test_clear_falls_back_to_env_default(self):
        asyncio.run(self.svc.update_settings({"JIMENG_T2I_MODEL": "custom_t2i_key"}))
        overview = asyncio.run(self.svc.update_settings({"JIMENG_T2I_MODEL": ""}))

        item = next(i for i in overview["settings"] if i["key"] == "JIMENG_T2I_MODEL")
        self.assertFalse(item["overridden"])
        self.assertEqual(
            self.settings.jimeng_t2i_model,
            self.svc._ENV_DEFAULTS["JIMENG_T2I_MODEL"],
        )


if __name__ == "__main__":
    unittest.main()
