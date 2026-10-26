import asyncio
import importlib
import sys
import types
import unittest


class LlmFailureTest(unittest.TestCase):
    def setUp(self):
        # 保存真实模块，tearDown 还原，避免污染同进程后续测试
        self._saved = {
            name: sys.modules.get(name)
            for name in ("app.config", "openai", "tenacity")
        }

        fake_config = types.ModuleType("app.config")
        fake_config.settings = types.SimpleNamespace(
            llm_provider="doubao",
            has_ark_credentials=True,
            has_qwen_llm_credentials=True,
            qwen_text_model="qwen-plus",
            dashscope_llm_base_url="https://dashscope.example.test/compatible-mode/v1",
            dashscope_api_key="sk-test",
            ark_api_key="test-key",
            doubao_model="ep-test",
            doubao_api_base="https://ark.example.test/api/v3",
        )
        sys.modules["app.config"] = fake_config

        fake_openai = types.ModuleType("openai")
        fake_openai.APITimeoutError = TimeoutError
        fake_openai.APIConnectionError = ConnectionError
        fake_openai.RateLimitError = RuntimeError

        class AsyncOpenAI:
            def __init__(self, *args, **kwargs):
                pass

        fake_openai.AsyncOpenAI = AsyncOpenAI
        sys.modules["openai"] = fake_openai

        fake_tenacity = types.ModuleType("tenacity")
        fake_tenacity.retry = lambda *args, **kwargs: (lambda fn: fn)
        fake_tenacity.stop_after_attempt = lambda *args, **kwargs: None
        fake_tenacity.wait_exponential = lambda *args, **kwargs: None
        fake_tenacity.retry_if_exception_type = lambda *args, **kwargs: None
        sys.modules["tenacity"] = fake_tenacity

        sys.modules.pop("app.services.llm", None)
        self.llm = importlib.import_module("app.services.llm")

    def tearDown(self):
        for name, mod in self._saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)
        sys.modules.pop("app.services.llm", None)

    def test_analyze_product_raises_when_llm_connection_fails(self):
        async def failing_call(*args, **kwargs):
            raise ConnectionError("Connection error")

        self.llm._call_llm = failing_call

        with self.assertRaises(ConnectionError):
            asyncio.run(self.llm.analyze_product("给玩偶做商品图"))

    def test_generate_prompt_raises_when_llm_connection_fails(self):
        async def failing_call(*args, **kwargs):
            raise ConnectionError("Connection error")

        self.llm._call_llm = failing_call

        with self.assertRaises(ConnectionError):
            asyncio.run(self.llm.generate_prompt({"product_type": "玩偶", "visual_keywords": ["礼物"]}))


if __name__ == "__main__":
    unittest.main()
