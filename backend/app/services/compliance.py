"""文案合规过滤（需求 v2 F-C2）。

双层实现：
1) LLM 生成时在 system prompt 注入合规规则（软约束，见 llm.COPYWRITING_PROMPT）；
2) 生成后规则词库硬校验（本模块），命中广告法极限词标记违规并给出替换建议，
   由前端标红展示。

词库来源：kb/电商合规规则.md「绝对化用语禁用清单」，替换建议对齐其「替换为」列表。
"""

# (禁用词, 替换建议)，长词在前避免被短词提前命中（子串检测互相独立，顺序仅影响可读性）
COMPLIANCE_WORDS: list[dict] = [
    {"word": "国家级", "suggestion": "删除（需资质背书）"},
    {"word": "100倍", "suggestion": "多倍"},
    {"word": "100%", "suggestion": "大部分"},
    {"word": "99%", "suggestion": "约"},
    {"word": "唯一", "suggestion": "之一"},
    {"word": "第一", "suggestion": "排名靠前"},
    {"word": "绝对", "suggestion": "较为"},
    {"word": "彻底", "suggestion": "深入"},
    {"word": "完全", "suggestion": "较为"},
    {"word": "无敌", "suggestion": "出色"},
    {"word": "顶级", "suggestion": "高品质"},
    {"word": "极致", "suggestion": "出色"},
    {"word": "完美", "suggestion": "优质"},
    {"word": "只有", "suggestion": "仅有"},
    {"word": "所有", "suggestion": "部分"},
    {"word": "最", "suggestion": "较为"},
    {"word": "特效", "suggestion": "删除或具体描述"},
]


def check_compliance(text: str) -> dict:
    """对一段文本做极限词硬校验。

    Returns:
        {
            "has_violation": bool,
            "violations": [{"word", "suggestion", "count"}, ...],
        }
    """
    if not text:
        return {"has_violation": False, "violations": []}

    violations = []
    for item in COMPLIANCE_WORDS:
        word = item["word"]
        count = text.count(word)
        if count > 0:
            violations.append(
                {"word": word, "suggestion": item["suggestion"], "count": count}
            )

    return {"has_violation": bool(violations), "violations": violations}


def compliance_rules_text() -> str:
    """生成注入 LLM system prompt 的合规规则摘要。"""
    banned = "、".join(w["word"] for w in COMPLIANCE_WORDS)
    replacements = "、".join(
        sorted({w["suggestion"] for w in COMPLIANCE_WORDS if "删除" not in w["suggestion"]})
    )
    return (
        f"严禁使用以下广告法绝对化用语：{banned}。"
        f"改用：{replacements} 等表述；涉及数据/功效宣称需可溯源，禁止医疗化暗示。"
    )