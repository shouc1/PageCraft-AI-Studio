"""营销热点静态日历（需求 v2 F-C3，P1 方案）。

零外部依赖的热点源：内置「节日 / 节气 / 大促」日历，按当前日期返回临近热点，
注入文案生成的用户提示，实现"临近双 11 突出囤货场景"等文案倾向。

P2 升级路径：换成豆包 web search 插件（ARK 联网工具），本模块可平滑替换。
"""

from datetime import date, timedelta

# 静态热点日历：month/day → 热点名、文案提示、类型
# 注：农历节日（中秋/春节等）按阳历近似日期维护，商用时需按年校准。
HOTSPOT_CALENDAR: dict[tuple[int, int], dict] = {
    # 电商大促
    (1, 15): {"name": "年货节", "hint": "突出囤货、家庭团聚、送礼场景", "type": "大促"},
    (3, 8): {"name": "女神节", "hint": "突出悦己、礼物、女性关怀场景", "type": "大促"},
    (6, 18): {"name": "618", "hint": "突出年中大促、囤货、性价比", "type": "大促"},
    (11, 11): {"name": "双十一", "hint": "突出囤货、优惠、全年最低氛围", "type": "大促"},
    (12, 12): {"name": "双十二", "hint": "突出年末清仓、最后一波优惠", "type": "大促"},
    # 节日
    (1, 1): {"name": "元旦", "hint": "突出新年焕新、开年礼物场景", "type": "节日"},
    (2, 14): {"name": "情人节", "hint": "突出浪漫、情侣礼物、仪式感场景", "type": "节日"},
    (5, 12): {"name": "母亲节", "hint": "突出母爱、感恩、送礼场景", "type": "节日"},
    (6, 20): {"name": "父亲节", "hint": "突出父爱、感恩、实用礼场景", "type": "节日"},
    (8, 8): {"name": "七夕", "hint": "突出浪漫、情侣礼物场景", "type": "节日"},
    (9, 10): {"name": "教师节", "hint": "突出感恩、谢师礼场景", "type": "节日"},
    (10, 1): {"name": "国庆", "hint": "突出出行、家庭、假期场景", "type": "节日"},
    (12, 25): {"name": "圣诞", "hint": "突出节日氛围、礼物、欢聚场景", "type": "节日"},
    # 节气（示例，可按需扩充）
    (11, 7): {"name": "立冬", "hint": "突出冬日、温暖、进补场景", "type": "节气"},
    (12, 22): {"name": "冬至", "hint": "突出团圆、温暖、传统习俗场景", "type": "节气"},
}

# 临近热点的时间窗（天）
_LOOKAHEAD_DAYS = 30


def _days_until(month: int, day: int, today: date) -> int:
    """距下一次该月-日事件的天数（跨年自动滚动到下一年）。"""
    target = date(today.year, month, day)
    if target < today:
        target = date(today.year + 1, month, day)
    return (target - today).days


def get_active_hotspots(today: date | None = None, lookahead: int = _LOOKAHEAD_DAYS) -> list[dict]:
    """返回临近（未来 lookahead 天内）的热点，按临近程度升序。

    Returns:
        [{"name", "hint", "type", "days_until"}, ...]
    """
    current = today or date.today()
    hotspots = []
    for (month, day), info in HOTSPOT_CALENDAR.items():
        days = _days_until(month, day, current)
        if 0 <= days <= lookahead:
            hotspots.append(
                {
                    "name": info["name"],
                    "hint": info["hint"],
                    "type": info["type"],
                    "days_until": days,
                }
            )
    hotspots.sort(key=lambda x: x["days_until"])
    return hotspots


def hotspot_hint_text(hotspots: list[dict], limit: int = 2) -> str:
    """将临近热点拼成一段可注入 LLM 的文案提示。"""
    if not hotspots:
        return ""
    parts = []
    for h in hotspots[:limit]:
        when = "临近" if h["days_until"] > 3 else "正值"
        parts.append(f"{when}{h['name']}，{h['hint']}")
    return "；".join(parts)