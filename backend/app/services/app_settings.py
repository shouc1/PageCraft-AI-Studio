"""运行时设置覆盖层（方案 B：DB 覆盖 > .env）。

语义：
- .env 是出厂默认值，app_settings 表是用户自定义值
- 启动时：config.py 先从 .env 构造 settings，本模块再把 DB 覆盖原地应用到单例
- 用户在设置页修改 → 写 DB + 原地更新单例，立即生效（无需重启）
- 用户清除某项（空字符串）→ 删除 DB 记录，回落 .env 默认值
- .env 后来手动修改只对「没有 DB 覆盖」的字段生效
"""

from datetime import datetime, timezone

from app.config import settings
from app.database import get_db
from app.logger import logger

# 允许运行时编辑的字段：DB 键（env 风格大写）→ Settings 字段名
EDITABLE_FIELDS: dict[str, str] = {
    "ARK_API_KEY": "ark_api_key",
    "DOUBAO_MODEL": "doubao_model",
    "VOLCENGINE_AK": "volcengine_ak",
    "VOLCENGINE_SK": "volcengine_sk",
    "JIMENG_T2I_MODEL": "jimeng_t2i_model",
    "JIMENG_I2I_MODEL": "jimeng_i2i_model",
    "IMAGE_PROVIDER": "image_provider",
    "LLM_PROVIDER": "llm_provider",
    "DASHSCOPE_API_KEY": "dashscope_api_key",
    "QWEN_IMAGE_MODEL": "qwen_image_model",
    "QWEN_TEXT_MODEL": "qwen_text_model",
}

# 厂商枚举（key → 合法值）
PROVIDER_ENUMS = {
    "IMAGE_PROVIDER": ("jimeng", "qwen"),
    "LLM_PROVIDER": ("doubao", "qwen"),
}

# 密钥类字段：查询接口脱敏返回
SECRET_FIELDS = {"ARK_API_KEY", "VOLCENGINE_AK", "VOLCENGINE_SK", "DASHSCOPE_API_KEY"}

# .env 出厂默认值快照（模块导入时捕获，此时 DB 覆盖尚未应用）
_ENV_DEFAULTS: dict[str, str] = {
    key: getattr(settings, field) for key, field in EDITABLE_FIELDS.items()
}


def mask_secret(value: str) -> str:
    """密钥脱敏：保留首尾各 4 位，中间打码；过短全部打码。"""
    if not value:
        return ""
    if len(value) <= 8:
        return "••••"
    return f"{value[:4]}••••{value[-4:]}"


def _apply(key: str, value: str) -> None:
    """原地更新 settings 单例字段（可编辑项均为 str，直接赋值即时生效）。"""
    setattr(settings, EDITABLE_FIELDS[key], value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def load_overrides() -> int:
    """启动时调用（lifespan，init_db 之后）：把 DB 覆盖应用到 settings 单例。

    Returns:
        应用的覆盖条数。
    """
    db = await get_db()
    try:
        cursor = await db.execute("SELECT key, value FROM app_settings")
        rows = await cursor.fetchall()
    finally:
        await db.close()

    applied = 0
    for row in rows:
        key = row["key"]
        if key in EDITABLE_FIELDS:
            _apply(key, row["value"])
            applied += 1
        else:
            logger.warning("设置覆盖层发现未知键 %s，已忽略", key)
    if applied:
        logger.info("已应用 %d 条运行时设置覆盖（DB 优先于 .env）", applied)
    return applied


async def get_settings_overview() -> dict:
    """各可编辑字段的生效值（密钥脱敏）+ 是否被 DB 覆盖 + .env 默认值。"""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT key FROM app_settings")
        overridden = {row["key"] for row in await cursor.fetchall()}
    finally:
        await db.close()

    items = []
    for key, _field in EDITABLE_FIELDS.items():
        effective = getattr(settings, EDITABLE_FIELDS[key])
        is_secret = key in SECRET_FIELDS
        items.append(
            {
                "key": key,
                "value": mask_secret(effective) if is_secret else effective,
                "overridden": key in overridden,
                "env_default": mask_secret(_ENV_DEFAULTS[key]) if is_secret else _ENV_DEFAULTS[key],
            }
        )
    return {
        "has_credentials": settings.has_credentials,
        "has_ark_credentials": settings.has_ark_credentials,
        "has_dashscope_credentials": settings.has_dashscope_credentials,
        "has_qwen_llm_credentials": settings.has_qwen_llm_credentials,
        "llm_provider": settings.llm_provider,
        "image_provider": settings.image_provider,
        "settings": items,
    }


async def update_settings(values: dict[str, str]) -> dict:
    """部分更新设置：非空写 DB + 原地更新单例；空字符串删覆盖回落 .env。

    Raises:
        ValueError: 包含不支持的设置键。
    """
    unknown = [k for k in values if k not in EDITABLE_FIELDS]
    if unknown:
        raise ValueError(f"不支持的设置项：{', '.join(unknown)}")

    # 厂商枚举校验
    for key, allowed in PROVIDER_ENUMS.items():
        v = values.get(key, "").strip()
        if v and v not in allowed:
            raise ValueError(f"{key} 仅支持 {' / '.join(allowed)}")

    db = await get_db()
    try:
        for key, raw_value in values.items():
            value = raw_value.strip()
            if value == "":
                await db.execute("DELETE FROM app_settings WHERE key = ?", (key,))
                _apply(key, _ENV_DEFAULTS[key])
                logger.info("设置 %s 已清除，回落 .env 默认值", key)
            else:
                await db.execute(
                    "INSERT INTO app_settings(key, value, updated_at) VALUES(?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                    (key, value, _now()),
                )
                _apply(key, value)
                log_value = "***" if key in SECRET_FIELDS else value
                logger.info("设置 %s 已更新（%s）", key, log_value)
        await db.commit()
    finally:
        await db.close()

    return await get_settings_overview()
