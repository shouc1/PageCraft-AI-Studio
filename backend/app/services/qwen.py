"""阿里云百炼 DashScope 千问生图客户端（qwen-image 系列）。

契约（已查证官方文档，2026-10）：
- POST {base_url}/services/aigc/multimodal-generation/generation，Bearer sk-xxx 鉴权
- 同步返回，output.choices[0].message.content[].image 为 OSS URL（24h 有效，需立即下载）
- input.messages 单轮，content 数组：文生图仅 {"text": prompt}；
  图生图 1~3 张 {"image": URL 或 base64 dataURI} + {"text": prompt}
- size 用 "*" 分隔（如 1024*1024）
- qwen-image-3.0-pro 同一模型支持文生图与图生图；无重绘强度参数，strength 忽略
"""

import base64
import uuid
from pathlib import Path

import httpx

from app.config import settings
from app.logger import logger

# 千问图生图最多 3 张参考图
MAX_INPUT_IMAGES = 3


def _convert_size(size: str | None) -> str:
    """项目内部尺寸格式 1024x1024 → 千问格式 1024*1024。"""
    if not size:
        return "1024*1024"
    return size.replace("x", "*").replace("X", "*")


def build_qwen_payload(
    workflow: str,
    prompt: str,
    image_data_uris: list[str] | None,
    size: str | None = None,
) -> dict:
    """构造千问 multimodal-generation 请求体（纯函数，便于测试）。"""
    content: list[dict] = []
    if workflow == "image2image":
        if not image_data_uris:
            raise ValueError("image2image requires input_image")
        for uri in image_data_uris[:MAX_INPUT_IMAGES]:
            content.append({"image": uri})
    elif workflow != "text2image":
        raise ValueError(f"Unsupported workflow: {workflow}")

    content.append({"text": prompt})
    return {
        "model": settings.qwen_image_model,
        "input": {
            "messages": [
                {"role": "user", "content": content}
            ]
        },
        "parameters": {
            # 项目已用豆包三专家流水线扩写 prompt，关闭千问自带扩写避免二次改写
            "prompt_extend": False,
            "watermark": False,
            "size": _convert_size(size),
        },
    }


async def generate(
    workflow: str,
    prompt: str,
    input_images: list[str] | None = None,
    strength: float | None = None,
    size: str | None = None,
) -> tuple[Path, dict]:
    """调用千问生成图片，返回（本地结果路径，元数据）。

    签名与 jimeng.generate 对齐（strength 接收但忽略，千问无重绘强度参数）。

    Args:
        workflow: image2image / text2image
        prompt: 扩展后的 prompt
        input_images: 参考图文件名列表（image2image，最多取前 3 张）
        size: 生图尺寸，如 "1024x1024"
    """
    if not settings.has_dashscope_credentials:
        raise RuntimeError("千问生图未配置，请检查 DASHSCOPE_API_KEY 和 QWEN_IMAGE_MODEL")

    # 读取参考图并转 base64 dataURI
    image_data_uris: list[str] = []

    def _resolve_image_path(filename: str) -> Path | None:
        for directory in (settings.upload_dir, settings.result_dir):
            path = directory / filename
            if path.exists():
                return path
        return None

    for filename in input_images or []:
        path = _resolve_image_path(filename)
        if path:
            b64 = base64.b64encode(path.read_bytes()).decode()
            image_data_uris.append(f"data:image/png;base64,{b64}")

    payload = build_qwen_payload(workflow, prompt, image_data_uris or None, size)
    url = f"{settings.dashscope_base_url.rstrip('/')}/services/aigc/multimodal-generation/generation"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.dashscope_api_key}",
    }

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error("千问生图失败 HTTP %d: %s", resp.status_code, resp.text)
            raise RuntimeError(f"千问生图失败 HTTP {resp.status_code}: {resp.text}")
        data = resp.json()

    choices = data.get("output", {}).get("choices", [])
    content = (choices[0].get("message", {}) if choices else {}).get("content", [])
    image_urls = [c["image"] for c in content if isinstance(c, dict) and c.get("image")]
    if not image_urls:
        raise RuntimeError(f"千问生图返回中无图像：{data}")

    # 结果 URL 24h 有效，立即下载到本地（千问返回 PNG）
    result_dir: Path = settings.result_dir
    result_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    local_path = result_dir / filename
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(image_urls[0])
        resp.raise_for_status()
        local_path.write_bytes(resp.content)

    logger.info("千问生图完成：%s（workflow=%s）", filename, workflow)
    return local_path, {"provider": "qwen", "model": settings.qwen_image_model}
