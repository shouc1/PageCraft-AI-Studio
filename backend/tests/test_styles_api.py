"""风格库服务测试（解析 / 编辑写回 / 推荐排序）。

全部用临时目录隔离，不触碰真实 kb 文件与 RAG 索引：
- 解析与推荐测试 patch KB_DIR + CATEGORY_MAP + RAG 可用性
- 编辑测试额外 no-op 掉索引重建调度
"""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# 风格块模板（两条，--- 分隔）
KB_CONTENT = """# 风格：测试极简风
- 适用商品：美妆、护肤品、文具
- 配色：莫兰迪色系，低饱和
- 元素：几何形、留白
- 光线：大平光柔光
- 背景：纯色背景
- 构图：极简留白
- prompt 模板：商品摄影，{product}，极简风格
- 负面提示：复杂背景

---

# 风格：测试赛博风
- 适用商品：数码产品、游戏外设
- 配色：深蓝、紫、霓虹色
- 元素：电路纹理、光线轨迹
- 光线：霓虹灯效
- 背景：深色科技纹理
- 构图：商品居中
- prompt 模板：product photography, {product}, cyberpunk
- 负面提示：rustic, natural light
"""


class StylesServiceTest(unittest.TestCase):
    def setUp(self):
        from app.services import styles as styles_svc
        from app.services import rag

        self.styles_svc = styles_svc
        self.rag = rag
        self._orig_kb_dir = styles_svc.KB_DIR
        self._orig_category_map = rag.CATEGORY_MAP
        self._orig_is_available = rag.is_available

    def tearDown(self):
        self.styles_svc.KB_DIR = self._orig_kb_dir
        self.rag.CATEGORY_MAP = self._orig_category_map
        self.rag.is_available = self._orig_is_available

    def _patch_kb(self, tmp: str):
        """临时 kb 目录 + 注册测试文件到 style_template 类目 + 禁用 RAG。"""
        kb_dir = Path(tmp)
        (kb_dir / "风格模板-测试.md").write_text(KB_CONTENT, encoding="utf-8")
        self.styles_svc.KB_DIR = kb_dir
        self.rag.CATEGORY_MAP = {
            **self._orig_category_map, "风格模板-测试.md": "style_template"
        }
        self.rag.is_available = lambda: False

    def test_list_entries(self):
        entries = self.styles_svc.list_style_entries()
        self.assertGreaterEqual(len(entries), 5)
        by_name = {e["name"]: e for e in entries}
        self.assertIn("极简ins风", by_name)
        entry = by_name["极简ins风"]
        self.assertIn("莫兰迪", entry["colors"])
        self.assertIn("{product}", entry["prompt_template"])
        self.assertTrue(entry["negative_prompt"])

    def test_recommend_keyword_fallback(self):
        async def run():
            ranked, rag_enabled = await self.styles_svc.recommend_and_rank("美妆", top_k=1)
            self.assertFalse(rag_enabled)
            self.assertEqual(ranked[0]["name"], "测试极简风")
            self.assertTrue(ranked[0]["recommended"])
            self.assertFalse(ranked[1]["recommended"])

        with tempfile.TemporaryDirectory() as tmp:
            self._patch_kb(tmp)
            asyncio.run(run())

    def test_recommend_no_query_no_recommendation(self):
        async def run():
            ranked, rag_enabled = await self.styles_svc.recommend_and_rank("", top_k=3)
            self.assertFalse(rag_enabled)
            self.assertTrue(all(not e["recommended"] for e in ranked))

        with tempfile.TemporaryDirectory() as tmp:
            self._patch_kb(tmp)
            asyncio.run(run())

    def test_update_style(self):
        async def run():
            updated = await self.styles_svc.update_style_entry(
                "测试极简风", {"colors": "纯白低饱和", "elements": "大理石纹"}
            )
            self.assertEqual(updated["colors"], "纯白低饱和")
            self.assertEqual(updated["elements"], "大理石纹")
            # 其他字段不受影响
            self.assertIn("{product}", updated["prompt_template"])
            # 文件写回：结构保持、另一条目未变
            content = (Path(tmp) / "风格模板-测试.md").read_text(encoding="utf-8")
            self.assertEqual(content.count("---"), 1)
            self.assertIn("- 配色：纯白低饱和", content)
            self.assertIn("# 风格：测试赛博风", content)
            self.assertIn("- 配色：深蓝、紫、霓虹色", content)
            # 二次解析可见
            again = self.styles_svc.get_style_entry("测试极简风")
            self.assertEqual(again["colors"], "纯白低饱和")

        with tempfile.TemporaryDirectory() as tmp:
            self._patch_kb(tmp)
            # no-op 索引重建调度，避免测试触发真实 RAG 重建
            self.styles_svc._schedule_rebuild = lambda: None
            asyncio.run(run())

    def test_update_style_append_missing_field(self):
        async def run():
            content = (Path(tmp) / "风格模板-测试.md").read_text(encoding="utf-8")
            content = content.replace("- 负面提示：复杂背景\n", "")
            (Path(tmp) / "风格模板-测试.md").write_text(content, encoding="utf-8")

            updated = await self.styles_svc.update_style_entry(
                "测试极简风", {"negative_prompt": "高饱和，强阴影"}
            )
            self.assertEqual(updated["negative_prompt"], "高饱和，强阴影")
            raw = (Path(tmp) / "风格模板-测试.md").read_text(encoding="utf-8")
            self.assertIn("- 负面提示：高饱和，强阴影", raw)

        with tempfile.TemporaryDirectory() as tmp:
            self._patch_kb(tmp)
            self.styles_svc._schedule_rebuild = lambda: None
            asyncio.run(run())

    def test_update_style_not_found(self):
        async def run():
            with self.assertRaises(LookupError):
                await self.styles_svc.update_style_entry("不存在的风格", {"colors": "x"})

        with tempfile.TemporaryDirectory() as tmp:
            self._patch_kb(tmp)
            asyncio.run(run())

    def test_update_style_invalid_values(self):
        async def run():
            with self.assertRaises(ValueError):
                await self.styles_svc.update_style_entry(
                    "测试极简风", {"colors": "a---b"}
                )
            with self.assertRaises(ValueError):
                await self.styles_svc.update_style_entry(
                    "测试极简风", {"colors": "a\nb"}
                )
            with self.assertRaises(ValueError):
                await self.styles_svc.update_style_entry(
                    "测试极简风", {"prompt_template": ""}
                )
            # 校验失败不应写文件
            raw = (Path(tmp) / "风格模板-测试.md").read_text(encoding="utf-8")
            self.assertIn("- 配色：莫兰迪色系，低饱和", raw)

        with tempfile.TemporaryDirectory() as tmp:
            self._patch_kb(tmp)
            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
