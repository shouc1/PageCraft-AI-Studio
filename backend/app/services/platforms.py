"""电商平台生图尺寸规格（需求 v2 §6.5）。

主图 1:1，但各平台推荐尺寸不同；生成时按平台选择对应尺寸，
未指定平台则用 settings.main_image_size（1024x1024）。

规格来源：kb/电商主图规范.md（取"推荐"档）。
"""

# 平台 → 主图推荐尺寸（kb/电商主图规范.md）
PLATFORM_SIZES: dict[str, str] = {
    "taobao": "1200x1200",   # 淘宝/天猫推荐
    "tmall": "1200x1200",    # 天猫同淘宝
    "jd": "1200x1200",       # 京东推荐
    "pdd": "750x750",        # 拼多多主图
    "douyin": "1080x1080",   # 抖音推荐
}


def resolve_platform_size(platform: str | None, default_size: str | None = None) -> str | None:
    """根据平台返回主图尺寸；未知平台返回 default_size。"""
    if not platform:
        return default_size
    return PLATFORM_SIZES.get(platform.lower(), default_size)