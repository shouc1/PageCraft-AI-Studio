"""详情页结构规划（需求 v2 F-D1）。

由类目决定详情页的 6 张结构模板（每张图的定位 + 说明 + 生图提示骨架），
供前端展示，用户可增删/调整每张图定位后再确认生成。

模板来源：需求 v2 §3.2 给出的三个类目示例 + 类目常识补全。
"""

# 类目 → 详情页 6 张结构模板
DETAIL_PAGE_TEMPLATES: dict[str, list[dict]] = {
    "数码电子": [
        {"slot": "场景图", "desc": "产品融入真实使用场景", "prompt_hint": "真实使用场景，产品自然融入"},
        {"slot": "场景图", "desc": "第二使用场景，覆盖更多人群", "prompt_hint": "另一使用场景，突出不同人群"},
        {"slot": "参数特写", "desc": "核心参数放大展示", "prompt_hint": "产品局部特写，突出质感与工艺"},
        {"slot": "参数特写", "desc": "接口/功能细节特写", "prompt_hint": "细节特写，突出功能部件"},
        {"slot": "功能对比", "desc": "关键功能对比表达", "prompt_hint": "功能对比示意图，客观呈现"},
        {"slot": "售后承诺", "desc": "售后与保障信息展示", "prompt_hint": "服务保障元素，可信赖氛围"},
    ],
    "服装鞋包": [
        {"slot": "上身场景", "desc": "模特上身整体效果", "prompt_hint": "模特上身场景，自然姿态"},
        {"slot": "上身场景", "desc": "第二搭配场景", "prompt_hint": "另一搭配场景，突出风格"},
        {"slot": "材质细节", "desc": "面料材质放大特写", "prompt_hint": "面料纹理特写，突出质感"},
        {"slot": "材质细节", "desc": "缝线/五金细节", "prompt_hint": "工艺细节特写"},
        {"slot": "版型展示", "desc": "版型/剪裁立体展示", "prompt_hint": "立体版型展示"},
        {"slot": "尺码洗涤", "desc": "尺码表与洗涤说明", "prompt_hint": "信息图表风格，清晰规范"},
    ],
    "食品饮料": [
        {"slot": "食用场景", "desc": "食用/饮用场景", "prompt_hint": "食用场景，氛围自然"},
        {"slot": "食用场景", "desc": "第二使用场景", "prompt_hint": "另一食用场景，突出便携/分享"},
        {"slot": "配料产地", "desc": "配料/产地放大展示", "prompt_hint": "原料特写，突出新鲜与产地"},
        {"slot": "配料产地", "desc": "原料溯源细节", "prompt_hint": "原料细节特写"},
        {"slot": "工艺展示", "desc": "制作工艺展示", "prompt_hint": "工艺过程展示，突出匠心"},
        {"slot": "规格参数", "desc": "规格/营养成分展示", "prompt_hint": "信息图表风格，规格参数清晰"},
    ],
    "家居家电": [
        {"slot": "使用场景", "desc": "家居使用场景", "prompt_hint": "家居场景，自然融入"},
        {"slot": "使用场景", "desc": "第二功能场景", "prompt_hint": "另一使用场景，突出多功能"},
        {"slot": "材质工艺", "desc": "材质/工艺特写", "prompt_hint": "材质质感特写"},
        {"slot": "材质工艺", "desc": "细节部件特写", "prompt_hint": "细节工艺特写"},
        {"slot": "功能演示", "desc": "核心功能演示", "prompt_hint": "功能演示示意"},
        {"slot": "规格参数", "desc": "尺寸/参数信息", "prompt_hint": "信息图表风格，参数清晰"},
    ],
    "美妆护肤": [
        {"slot": "使用场景", "desc": "使用场景/氛围", "prompt_hint": "使用场景，氛围自然"},
        {"slot": "使用场景", "desc": "第二使用场景", "prompt_hint": "另一使用场景，突出效果氛围"},
        {"slot": "质地细节", "desc": "产品质地/膏体特写", "prompt_hint": "质地特写，突出细腻"},
        {"slot": "质地细节", "desc": "包装/细节特写", "prompt_hint": "包装细节特写，突出高级感"},
        {"slot": "功效特写", "desc": "核心功效可视化", "prompt_hint": "功效可视化表达，客观克制"},
        {"slot": "成分规格", "desc": "成分/规格信息", "prompt_hint": "信息图表风格，成分清晰"},
    ],
}

# 兜底模板：未知类目用通用结构
_DEFAULT_TEMPLATE = [
    {"slot": "场景图", "desc": "使用场景展示", "prompt_hint": "使用场景，自然呈现"},
    {"slot": "场景图", "desc": "第二场景展示", "prompt_hint": "另一场景，丰富视角"},
    {"slot": "细节特写", "desc": "材质/工艺细节", "prompt_hint": "细节特写，突出质感"},
    {"slot": "细节特写", "desc": "局部细节", "prompt_hint": "局部细节特写"},
    {"slot": "功能展示", "desc": "功能/特点展示", "prompt_hint": "功能展示示意"},
    {"slot": "规格信息", "desc": "规格/参数信息", "prompt_hint": "信息图表风格，清晰规范"},
]


def get_detail_plan(category: str) -> dict:
    """返回类目对应的详情页结构规划（6 张），未知类目用兜底模板。"""
    template = DETAIL_PAGE_TEMPLATES.get(category, _DEFAULT_TEMPLATE)
    slots = [
        {"index": i, **slot} for i, slot in enumerate(template)
    ]
    return {"category": category, "slots": slots}