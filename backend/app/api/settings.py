"""运行时设置路由：查看/修改豆包与即梦凭证（DB 覆盖层 > .env，改后即时生效）。

- GET /api/settings   各可编辑项生效值（密钥脱敏）+ 是否被覆盖 + 凭证就绪状态
- PUT /api/settings   部分更新；空字符串表示清除覆盖、回落 .env 默认值
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.logger import logger
from app.services import app_settings as settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdateRequest(BaseModel):
    values: dict[str, str] = Field(
        ...,
        description="设置键 → 新值；密钥传空字符串表示清除覆盖回落 .env",
    )


@router.get("")
async def get_settings():
    """查看运行时设置：生效值（密钥脱敏）、覆盖状态、凭证就绪状态。"""
    return await settings_service.get_settings_overview()


@router.put("")
async def update_settings(body: SettingsUpdateRequest):
    """部分更新设置，写库后原地更新配置单例，立即生效（无需重启）。"""
    if not body.values:
        raise HTTPException(status_code=400, detail="values 不能为空")

    try:
        overview = await settings_service.update_settings(body.values)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info("运行时设置已更新：%s", ", ".join(body.values.keys()))
    return {"status": "ok", **overview}
