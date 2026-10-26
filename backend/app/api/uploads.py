"""图片上传路由。"""

import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.config import settings
from app.logger import logger

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

MAX_SIZE = 10 * 1024 * 1024  # 10MB

# 文件头魔数 → 扩展名（防止伪造 content_type 上传恶意文件）
_MAGIC_NUMBERS = {
    b"\xff\xd8\xff": "jpg",           # JPEG
    b"\x89PNG": "png",                # PNG
    b"RIFF": "webp",                  # WebP (RIFF....WEBP)
}


def _detect_image_type(content: bytes) -> str | None:
    """通过文件头魔数检测真实图片类型（不信任 content_type）。"""
    if content[:3] == b"\xff\xd8\xff":
        return "jpg"
    if content[:4] == b"\x89PNG":
        return "png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    return None


@router.post("")
async def upload_image(file: UploadFile = File(...)):
    """上传图片，返回文件名（后续创建任务时传 input_image）。"""
    content = await file.read()

    # 1. 大小校验
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="图片不能超过 10MB")

    # 2. 魔数校验（防止伪造 content_type 上传恶意文件）
    real_type = _detect_image_type(content)
    if real_type is None:
        raise HTTPException(status_code=400, detail="仅支持 JPG / PNG / WebP 格式")

    filename = f"img_{uuid.uuid4().hex[:12]}.{real_type}"
    save_path = settings.upload_dir / filename
    save_path.write_bytes(content)

    logger.info("图片上传：%s (%s, %dKB)", filename, real_type, len(content) // 1024)
    return {"filename": filename, "url": f"/api/uploads/{filename}"}


@router.get("/{filename}")
async def serve_image(filename: str):
    """访问上传的图片（前端 <img src> 用）。"""
    from fastapi.responses import FileResponse

    # 防止路径穿越
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    path = settings.upload_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path)
