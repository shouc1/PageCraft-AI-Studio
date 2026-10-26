"""Jimeng workflow request adapters.

This module is intentionally pure: it only turns internal workflow inputs into
Volcengine request metadata and JSON bodies. Network, signing, and file IO stay
in `jimeng.py`.
"""

from dataclasses import dataclass
import re

from app.config import settings


@dataclass(frozen=True)
class JimengRequest:
    action: str
    version: str
    result_action: str
    result_version: str
    body: dict


def _parse_size(size: str | None) -> tuple[int, int]:
    if not size:
        return 1024, 1024
    numbers = [int(n) for n in re.findall(r"\d+", size)]
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    return 1024, 1024


def _clamp_strength(strength: float | None) -> float:
    if strength is None:
        return 0.6
    return min(max(float(strength), 0.1), 1.0)


def build_jimeng_request(
    workflow: str,
    prompt: str,
    input_images_b64: list[str] | None,
    size: str | None = None,
    strength: float | None = None,
) -> JimengRequest:
    """Build a Jimeng request for text2image or image2image.

    Args:
        input_images_b64: 参考图 base64 列表（image2image 支持多参考图融合，
                          需求 v2 §5 多图提升一致性）。
        strength: i2i 重绘强度，需求 v2 §5 压低到 0.3~0.5 保真商品本体。
    """
    width, height = _parse_size(size)
    if workflow == "text2image":
        return JimengRequest(
            action="CVSync2AsyncSubmitTask",
            version="2022-08-31",
            result_action="CVSync2AsyncGetResult",
            result_version="2022-08-31",
            body={
                "req_key": settings.jimeng_t2i_model,
                "prompt": prompt,
                "width": width,
                "height": height,
                "force_single": True,
            },
        )

    if workflow == "image2image":
        if not input_images_b64:
            raise ValueError("image2image requires input_image")
        return JimengRequest(
            action="JimengI2IV30SubmitTask",
            version="2024-06-06",
            result_action="JimengI2IV30GetResult",
            result_version="2024-06-06",
            body={
                "req_key": settings.jimeng_i2i_model,
                "prompt": prompt,
                "width": width,
                "height": height,
                "scale": _clamp_strength(strength),
                "binary_data_base64": input_images_b64,
            },
        )

    raise ValueError(f"Unsupported workflow: {workflow}")
