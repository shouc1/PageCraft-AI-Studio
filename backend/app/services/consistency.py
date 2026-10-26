"""物品一致性校验（需求 v2 §5.2）。

对生成结果图与原图做视觉 embedding 相似度比对，低于阈值标记"疑似失真"，
提示用户复查，避免 LOGO/文字失真、颜色/形状偏移、多图不一致。

实现策略：
- 优先使用视觉 embedding 模型（CLIP，sentence-transformers），本地模型目录
  models/clip-ViT-B-32 存在时启用；否则返回 available=False（不阻断生成）。
- 视觉模型未就绪时不做像素级伪造比对，诚实返回"未启用"，
  由前端仅提示"一致性校验未启用"，避免虚假的相似度数值。
"""

import asyncio
from pathlib import Path

from app.config import settings
from app.logger import logger

# 视觉 embedding 模型目录（与 rag 用文本模型区分，需单独部署 CLIP）
_VISUAL_MODEL_DIR = None
_visual_model = None
_available_checked = False


def _load_visual_model():
    """按需加载一次 CLIP 视觉模型（内存常驻）。"""
    global _visual_model, _available_checked, _VISUAL_MODEL_DIR
    if _available_checked:
        return _visual_model
    _available_checked = True

    try:
        from sentence_transformers import SentenceTransformer
        from app.config import BASE_DIR

        model_dir = BASE_DIR / "models" / "clip-ViT-B-32"
        if model_dir.exists():
            _visual_model = SentenceTransformer(str(model_dir), device="cpu")
            _VISUAL_MODEL_DIR = str(model_dir)
            logger.info("已加载视觉 embedding 模型：clip-ViT-B-32")
        else:
            logger.warning(
                "视觉 embedding 模型未部署（models/clip-ViT-B-32 不存在），一致性校验未启用"
            )
    except Exception as e:
        logger.warning("加载视觉 embedding 模型失败，一致性校验未启用：%s", e)
        _visual_model = None

    return _visual_model


def _cosine_similarity(a, b) -> float:
    """余弦相似度（numpy 向量）。"""
    import numpy as np

    a = np.asarray(a, dtype=float).flatten()
    b = np.asarray(b, dtype=float).flatten()
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _check_sync(source_path: Path, generated_path: Path) -> dict:
    """同步执行相似度比对（由 check_consistency 通过 to_thread 在线程中调用）。"""
    model = _load_visual_model()
    if model is None:
        return {
            "available": False,
            "similarity": None,
            "distortion_suspected": None,
            "method": "unavailable",
        }

    if not source_path.exists() or not generated_path.exists():
        return {"available": False, "similarity": None, "distortion_suspected": None, "method": "missing_file"}

    emb_source = model.encode(str(source_path))
    emb_gen = model.encode(str(generated_path))
    similarity = _cosine_similarity(emb_source, emb_gen)

    threshold = float(settings.consistency_threshold)
    return {
        "available": True,
        "similarity": round(similarity, 4),
        "threshold": threshold,
        "distortion_suspected": similarity < threshold,
        "method": "clip_cosine",
    }


async def check_consistency(source_path: str | Path, generated_path: str | Path) -> dict:
    """比对原图与生成图的视觉相似度。

    Returns:
        {
            "available": bool,          # 视觉模型是否就绪
            "similarity": float | None, # 余弦相似度 0~1
            "threshold": float | None,  # 判定阈值
            "distortion_suspected": bool | None,  # 是否疑似失真
            "method": str,              # 使用的方法
        }
    """
    src = Path(source_path)
    gen = Path(generated_path)
    try:
        return await asyncio.to_thread(_check_sync, src, gen)
    except Exception as e:
        logger.warning("一致性校验执行失败：%s", e)
        return {"available": False, "similarity": None, "distortion_suspected": None, "method": "error"}