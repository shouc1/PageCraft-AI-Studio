"""负面提示并入正向 prompt 的单元测试（graph.finalize 链路）。"""

import asyncio
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.services.graph import finalize_node, merge_negative_into_positive


class MergeNegativeTest(unittest.TestCase):
    def test_basic_merge(self):
        result = merge_negative_into_positive("一瓶精华液，纯白背景", "模糊、水印、文字")
        self.assertEqual(result, "一瓶精华液，纯白背景\n画面中避免出现：模糊、水印、文字。")

    def test_empty_negative_returns_original(self):
        self.assertEqual(merge_negative_into_positive("主体描述", ""), "主体描述")
        self.assertEqual(merge_negative_into_positive("主体描述", "   "), "主体描述")
        self.assertEqual(merge_negative_into_positive("主体描述", None), "主体描述")

    def test_trailing_punctuation_stripped(self):
        result = merge_negative_into_positive("主体", "模糊、水印。；")
        self.assertEqual(result, "主体\n画面中避免出现：模糊、水印。")

    def test_positive_trailing_whitespace_normalized(self):
        result = merge_negative_into_positive("主体描述  \n", "水印")
        self.assertEqual(result, "主体描述\n画面中避免出现：水印。")

    def test_finalize_node_merges(self):
        state = {
            "prompt": {
                "positive_prompt": "保留原图产品外观，纯白背景",
                "negative_prompt": "变形、卡通手绘",
            }
        }
        result = asyncio.run(finalize_node(state))
        self.assertIn("画面中避免出现：变形、卡通手绘。", result["final_prompt"])
        self.assertTrue(result["final_prompt"].startswith("保留原图产品外观"))

    def test_finalize_node_without_negative(self):
        state = {"prompt": {"positive_prompt": "主体描述"}}
        result = asyncio.run(finalize_node(state))
        self.assertEqual(result["final_prompt"], "主体描述")

    def test_expert3_prompt_has_conflict_dimension(self):
        from app.services.llm import EXPERT3_PROMPT
        self.assertIn("正负一致性", EXPERT3_PROMPT)


if __name__ == "__main__":
    unittest.main()
