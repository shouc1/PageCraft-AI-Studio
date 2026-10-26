"""千问生图 payload 构造测试（qwen.build_qwen_payload 链路）。"""

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


class BuildQwenPayloadTest(unittest.TestCase):
    def setUp(self):
        """固定模型名，避免测试结果依赖本地 .env 的 QWEN_IMAGE_MODEL 改动。"""
        from app.config import settings
        self._orig_model = settings.qwen_image_model
        settings.qwen_image_model = "qwen-image-test-model"

    def tearDown(self):
        from app.config import settings
        settings.qwen_image_model = self._orig_model

    def test_text2image_payload_text_only(self):
        from app.services.qwen import build_qwen_payload

        payload = build_qwen_payload("text2image", "商品海报", None, "1024x1024")

        self.assertEqual(payload["model"], "qwen-image-test-model")
        messages = payload["input"]["messages"]
        self.assertEqual(len(messages), 1)
        content = messages[0]["content"]
        # 文生图：仅一条 text
        self.assertEqual(content, [{"text": "商品海报"}])
        # size 分隔符转换为 *；关闭千问自带扩写（项目有三专家流水线）
        self.assertEqual(payload["parameters"]["size"], "1024*1024")
        self.assertFalse(payload["parameters"]["prompt_extend"])
        self.assertFalse(payload["parameters"]["watermark"])

    def test_image2image_payload_images_then_text(self):
        from app.services.qwen import build_qwen_payload

        uris = ["data:image/png;base64,aaa", "data:image/png;base64,bbb"]
        payload = build_qwen_payload("image2image", "换背景", uris, "750x1200")

        content = payload["input"]["messages"][0]["content"]
        self.assertEqual(
            content,
            [
                {"image": "data:image/png;base64,aaa"},
                {"image": "data:image/png;base64,bbb"},
                {"text": "换背景"},
            ],
        )
        self.assertEqual(payload["parameters"]["size"], "750*1200")

    def test_image2image_caps_at_three_reference_images(self):
        from app.services.qwen import build_qwen_payload

        uris = [f"data:image/png;base64,{i}" for i in range(5)]
        payload = build_qwen_payload("image2image", "p", uris, None)

        content = payload["input"]["messages"][0]["content"]
        images = [c for c in content if "image" in c]
        self.assertEqual(len(images), 3)

    def test_image2image_requires_input_image(self):
        from app.services.qwen import build_qwen_payload

        with self.assertRaises(ValueError):
            build_qwen_payload("image2image", "p", None, None)

    def test_unknown_workflow_rejected(self):
        from app.services.qwen import build_qwen_payload

        with self.assertRaises(ValueError):
            build_qwen_payload("inpaint", "p", None, None)


class QwenProviderRoutingTest(unittest.TestCase):
    """IMAGE_PROVIDER 覆盖层：枚举校验 + task_runner 分发读取。"""

    def setUp(self):
        import asyncio
        import tempfile
        from app.config import settings
        from app.database import init_db

        self.settings = settings
        self._orig_provider = settings.image_provider
        self._orig_db_path = settings.db_path
        self._tmp = tempfile.TemporaryDirectory()
        settings.db_path = Path(self._tmp.name) / "test.db"
        asyncio.run(init_db())
        self._asyncio = asyncio

    def tearDown(self):
        self.settings.image_provider = self._orig_provider
        self.settings.db_path = self._orig_db_path
        self._tmp.cleanup()

    def test_provider_override_applies_immediately(self):
        from app.services import app_settings as svc

        overview = self._asyncio.run(
            svc.update_settings({"IMAGE_PROVIDER": "qwen"})
        )
        self.assertEqual(overview["image_provider"], "qwen")
        self.assertEqual(self.settings.image_provider, "qwen")

        # 清除回落 .env
        overview = self._asyncio.run(svc.update_settings({"IMAGE_PROVIDER": ""}))
        self.assertEqual(overview["image_provider"], self.svc_env_default())

    def svc_env_default(self):
        from app.services import app_settings as svc

        return svc._ENV_DEFAULTS["IMAGE_PROVIDER"]

    def test_invalid_provider_rejected(self):
        from app.services import app_settings as svc

        with self.assertRaises(ValueError):
            self._asyncio.run(svc.update_settings({"IMAGE_PROVIDER": "openai"}))

    def test_llm_provider_switch_updates_dispatch(self):
        """LLM_PROVIDER 覆盖后 llm._get_client/_llm_model 立即跟随。"""
        from app.services import app_settings as svc
        from app.services import llm as llm_svc

        self._asyncio.run(svc.update_settings({"LLM_PROVIDER": "qwen"}))
        self.assertEqual(self.settings.llm_provider, "qwen")
        self.assertEqual(llm_svc._llm_model(), self.settings.qwen_text_model)

        self._asyncio.run(svc.update_settings({"LLM_PROVIDER": "doubao"}))
        self.assertEqual(llm_svc._llm_model(), self.settings.doubao_model)

    def test_llm_provider_invalid_rejected(self):
        from app.services import app_settings as svc

        with self.assertRaises(ValueError):
            self._asyncio.run(svc.update_settings({"LLM_PROVIDER": "gpt"}))


if __name__ == "__main__":
    unittest.main()
