"""豆包 LLM 调用（火山引擎 ARK，OpenAI 兼容接口）。

三专家流水线 + 评审循环：
  专家 1 商品分析师 → 专家 2 视觉设计师 → 专家 3 质量评审员
  评审不通过回专家 2 重试，最多 2 次。

无密钥或调用失败时直接抛错。
"""

import json
from typing import Callable, Awaitable
from openai import AsyncOpenAI, APITimeoutError, APIConnectionError, RateLimitError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.config import settings
from app.logger import logger

# ─── System Prompts ───────────────────────────────────────

EXPERT1_PROMPT = """你是电商商品分析专家。根据用户需求，按照电商视觉策划 SOP 分析商品。

输出 JSON 格式，包含字段：
- product_type: 商品类型（如"无线蓝牙耳机""饮料瓶""化妆品"）
- key_selling_points: 核心卖点数组，每项是对象 {"point": "卖点名称", "visual_concept": "将该卖点翻译成具体的视觉表现元素，如降噪→蓝色声波屏蔽特效，低延迟→紫色电竞流光，防水→水滴飞溅特效"}，3~5 个
- target_audience: 目标受众
- usage_scenario: 使用场景（如"电商主图""海报""详情页"）
- conversion_driver: 转化驱动力类型，从以下选一："视觉驱动型"/"痛点驱动型"/"理性驱动型"/"情感价值型"
- style_lock: 风格锁对象，包含 primary_color, accent_color, product_ratio, lighting, forbidden
- visual_keywords: 视觉关键词列表（5~8 个，中文，要具体如"电光蓝边缘发光""金属磨砂质感""珠光白外壳"而非笼统的"科技感"）
- compliance_notes: 合规提示

合规要求：
- 普通食品：什么功能都不能说，不暗示功效
- 保健食品：只能说批文批准的功能
- 运动器材：避免医疗术语和治疗承诺
- 所有产品：禁用绝对化用语（唯一、最、第一、100%等）

只输出 JSON，不要解释。"""

EXPERT2_PROMPT = """你是商业摄影 prompt 工程师。根据商品分析结果和 Campaign Style Lock，生成详细的中文图片生成 prompt。

positive_prompt 必须按以下分层结构组织（用换行分隔，不要用小标题，直接写内容）：

1. 主体描述：产品名称、外观细节（颜色/材质/结构/标识/按键等）、产品占比（60%-80%）、构图位置
2. 场景：背景描述、光线体系、布光方式、构图方式
3. 卖点视觉元素：将每个卖点翻译成具体的视觉特效（这是最重要的部分！）
   - 不要写"突出XX功能"，要描述具体画面：如"耳机两侧环绕半透明淡蓝色波纹屏蔽声波特效，外侧灰色嘈杂声波被阻隔"
   - 每个卖点用独立的视觉元素表现，元素之间不冲突
4. 画质：分辨率、质感、风格、色彩控制

**核心要求：卖点必须视觉化。** 商品分析中的 key_selling_points 每一项都有 visual_concept，必须将其转化为 prompt 中的具体画面描述。

**图生图场景（输入有参考图）：** 必须在主体描述开头强调"保留原图产品的外观形态和品牌标识，保持产品设计细节不变，不改变产品外形"，并尽可能描述产品可能的外观特征（颜色、材质、结构）。

negative_prompt：中文，排除变形、改产品外形、模糊、水印、文字、多余杂物、划痕脏污、昏暗、刺眼强光、杂乱背景、色彩失真、卡通手绘等。

如果有评审反馈，请根据反馈调整 prompt。

输出 JSON 格式：
{"positive_prompt": "...", "negative_prompt": "..."}

只输出 JSON，不要解释。"""

EXPERT3_PROMPT = """你是 AI 图片生成质量评审专家。按照以下维度评审 prompt 质量。

评审维度（每项 0-100 分，任一低于 60 分则不通过）：
1. 卖点视觉化（最重要）：每个卖点是否翻译成了具体的视觉特效画面，而非笼统的"突出XX功能"。如只写"突出降噪"不通过，必须写"蓝色声波屏蔽特效"等具体画面。
2. 视觉第一落点：产品主体占比是否 60%-80%，视觉焦点是否明确
3. 风格一致性：色彩/光影是否锁定不漂移
4. 合规性：是否有绝对化用语、功效暗示等违规风险
5. 完整性：是否有主体外观描述、场景、卖点视觉元素、画质和负面 prompt
6. 正负一致性：positive_prompt 是否与 negative_prompt 冲突——如 negative 排除"文字"但 positive 描述"艺术字排版"、negative 排除"卡通"但 positive 要求"卡通渲染"。发现冲突必须在 issues 中指出并将该项打为低分，不通过。

输出 JSON 格式：
{"passed": true/false, "score": 0-100, "issues": ["问题1"], "suggestions": "简短建议"}

passed 判定标准：总分 ≥ 60 且无单项低于 60。评审要宽松，prompt 基本可用就通过。只输出 JSON，不要解释。"""


# ─── 工具函数 ──────────────────────────────────────────────

def _get_client() -> AsyncOpenAI:
    """按语言模型厂商返回客户端（调用时读单例，设置页切换即时生效）。"""
    if settings.llm_provider == "qwen":
        # DashScope OpenAI 兼容地址
        return AsyncOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_llm_base_url,
        )
    return AsyncOpenAI(
        api_key=settings.ark_api_key,
        base_url=settings.doubao_api_base,
    )


def _llm_model() -> str:
    return (
        settings.qwen_text_model
        if settings.llm_provider == "qwen"
        else settings.doubao_model
    )


def _ensure_llm_credentials() -> None:
    if settings.llm_provider == "qwen":
        if not settings.has_qwen_llm_credentials:
            raise RuntimeError(
                "千问 LLM 未配置，请检查 DASHSCOPE_API_KEY 和 QWEN_TEXT_MODEL"
            )
    elif not settings.has_ark_credentials:
        raise RuntimeError("豆包 ARK 未配置，请检查 ARK_API_KEY 和 DOUBAO_MODEL")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    # 仅重试网络类异常：超时、连接失败、限流
    # 业务异常（400 格式错误、500 服务端错误）不重试，直接降级
    retry=retry_if_exception_type((APITimeoutError, APIConnectionError, RateLimitError)),
    before_sleep=lambda rs: logger.warning(
        "LLM 调用失败（%s），第 %d 次重试...",
        rs.outcome.exception().__class__.__name__,
        rs.attempt_number,
    ),
)
async def _call_llm(system_prompt: str, user_content: str) -> str:
    """调当前厂商 LLM，返回原始文本（带差异化自动重试）。"""
    client = _get_client()
    response = await client.chat.completions.create(
        model=_llm_model(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.7,
        max_tokens=800,
        timeout=60,
    )
    return response.choices[0].message.content.strip()


def _parse_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON（容忍 markdown 代码块包裹）。"""
    text = text.strip()
    if text.startswith("```"):
        # 去掉 ```json ... ``` 包裹
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
    return json.loads(text)


# ─── 专家 1：商品分析师 ────────────────────────────────────

async def analyze_product(
    user_prompt: str,
    knowledge: list[str] | None = None,
) -> dict:
    """提取商品卖点、受众、场景、视觉关键词。

    Args:
        user_prompt: 用户输入
        knowledge: 合规规则知识（来自 RAG compliance 类别），帮助专家1输出合规的卖点
    """
    _ensure_llm_credentials()

    user_content = f"用户需求：{user_prompt}"
    # 注入合规规则知识，帮助专家1识别红线
    if knowledge:
        knowledge_text = "\n---\n".join(knowledge)
        user_content += f"\n\n合规规则参考（来自 RAG 检索，请严格遵守对应品类的合规红线）：\n{knowledge_text}"

    raw = await _call_llm(EXPERT1_PROMPT, user_content)
    return _parse_json(raw)


# ─── 专家 2：视觉设计师 ────────────────────────────────────

async def generate_prompt(
    analysis: dict,
    feedback: str = "",
    knowledge: list[str] | None = None,
    is_image_to_image: bool = False,
) -> dict:
    """基于分析结果 + RAG 知识生成 positive_prompt + negative_prompt。"""
    _ensure_llm_credentials()

    user_content = f"商品分析：{json.dumps(analysis, ensure_ascii=False)}"

    # 标记是否为图生图场景
    if is_image_to_image:
        user_content += "\n\n【场景：图生图】输入有参考商品图，请务必在 prompt 开头强调保留原图产品的外观、形态、品牌标识，只改变背景、光线和氛围。"
    # 加入 RAG 检索到的风格知识
    if knowledge:
        knowledge_text = "\n---\n".join(knowledge)
        user_content += f"\n\n风格知识库参考（来自 RAG 检索，请结合生成）：\n{knowledge_text}"

    if feedback:
        user_content += f"\n\n评审反馈（请据此调整）：{feedback}"

    raw = await _call_llm(EXPERT2_PROMPT, user_content)
    return _parse_json(raw)


# ─── 专家 3：质量评审员 ────────────────────────────────────

async def review_prompt(
    prompt: dict,
    analysis: dict,
    knowledge: list[str] | None = None,
) -> dict:
    """评审 prompt 质量。

    Args:
        prompt: 待审的 positive/negative prompt
        analysis: 商品分析结果
        knowledge: 主图 SOP + 平台规范知识（来自 RAG sop/platform_spec 类别），
                   帮助专家3用平台规范和评审标准打分
    """
    _ensure_llm_credentials()

    user_content = f"商品分析：{json.dumps(analysis, ensure_ascii=False)}\n待审 prompt：{json.dumps(prompt, ensure_ascii=False)}"
    # 注入主图 SOP + 平台规范，让评审有据可依
    if knowledge:
        knowledge_text = "\n---\n".join(knowledge)
        user_content += f"\n\n评审标准与平台规范参考（来自 RAG 检索，请据此打分）：\n{knowledge_text}"

    raw = await _call_llm(EXPERT3_PROMPT, user_content)
    return _parse_json(raw)


# ─── 编排：三专家流水线 + 评审循环 ─────────────────────────

# 进度回调类型：(step, message) -> None
# step: "analyzing" / "retrieving" / "designing" / "reviewing"
ProgressCallback = Callable[[str, str, dict | None], Awaitable[None]]


async def expand_prompt(
    user_prompt: str,
    on_progress: ProgressCallback | None = None,
    is_image_to_image: bool = False,
) -> str:
    """三专家流水线 + RAG 检索 + 评审循环，返回最终的 positive_prompt。

    使用 LangGraph StateGraph 编排：
      专家 1 分析 → RAG 检索 → 专家 2 生成 → 专家 3 评审 → 合格？
                                                          ├─ 是 → 返回
                                                          └─ 否 → 回专家 2（最多重试 1 次）
    """
    from app.services.graph import run_pipeline
    return await run_pipeline(user_prompt, on_progress, is_image_to_image)


# ─── P0：类目识别 + 卖点提取（需求 v2 F-M1 / F-M2）───────

CATEGORIZE_PROMPT = """你是电商商品类目识别专家。根据用户对商品的描述，从以下 5 个类目中选择最符合的类目：

家居家电 / 数码电子 / 服装鞋包 / 美妆护肤 / 食品饮料

输出 JSON 格式：
{"category": "最可能的类目名", "confidence": 0.0~1.0, "candidates": [{"category": "类目名", "confidence": 0.0~1.0}, ...]}

confidence 表示确信程度：>=0.7 表示较确定可自动采纳；<0.7 表示不确定，需要用户确认。
candidates 按置信度降序，给出 1~3 个候选。
只输出 JSON，不要解释。"""

SELLING_POINTS_PROMPT = """你是电商卖点提炼专家。根据商品类目和用户描述，提炼 3~5 个核心卖点。

输出 JSON 格式：
{"selling_points": [{"point": "卖点名称", "visual_concept": "该卖点的视觉化表现建议，如降噪→蓝色声波屏蔽特效"}]}

要求：
- 卖点要具体、可感知，避免空泛的"质量好"
- visual_concept 必须是可落地的画面描述，不能只写"突出XX"
- 若提供卖点视觉化词典，优先从中匹配对应卖点的视觉化写法
只输出 JSON，不要解释。"""


async def categorize_product(user_hint: str) -> dict:
    """识别商品类目，返回 {category, confidence, candidates}。

    基于文本描述分类；无描述时返回低置信度让用户确认。
    """
    hint = (user_hint or "").strip()
    _ensure_llm_credentials()

    # 无任何描述时，无法可靠分类，直接要求用户确认
    if not hint:
        return {
            "category": "",
            "confidence": 0.0,
            "candidates": [{"category": c, "confidence": 0.0} for c in ["家居家电", "数码电子", "服装鞋包", "美妆护肤", "食品饮料"]],
        }

    raw = await _call_llm(CATEGORIZE_PROMPT, f"商品描述：{hint}")
    result = _parse_json(raw)
    # 低置信度时标记需确认
    confidence = float(result.get("confidence", 0.0))
    return {
        "category": result.get("category", ""),
        "confidence": confidence,
        "candidates": result.get("candidates", []),
    }


async def extract_selling_points(
    category: str,
    user_hint: str = "",
    knowledge: list[str] | None = None,
) -> dict:
    """基于类目 + 用户描述提炼结构化卖点，返回 {selling_points: [{point, visual_concept}]}。

    Args:
        category: 商品类目
        user_hint: 用户补充描述
        knowledge: 卖点视觉化词典知识（RAG visual_dict 类别）
    """
    _ensure_llm_credentials()

    user_content = f"商品类目：{category or '未知'}\n用户描述：{user_hint or '无'}"
    if knowledge:
        knowledge_text = "\n---\n".join(knowledge)
        user_content += f"\n\n卖点视觉化词典参考（请优先从中匹配视觉化写法）：\n{knowledge_text}"

    raw = await _call_llm(SELLING_POINTS_PROMPT, user_content)
    result = _parse_json(raw)
    points = result.get("selling_points", [])
    # 归一化，容忍 LLM 字段差异
    normalized = [
        {
            "point": (p.get("point") or "").strip(),
            "visual_concept": (p.get("visual_concept") or p.get("visual") or "").strip(),
        }
        for p in points
        if (p.get("point") or "").strip()
    ]
    return {"selling_points": normalized}


# ─── P1：营销文案生成 3 方案（需求 v2 F-C1）──────────────

COPYWRITING_PROMPT = """你是资深电商文案策划。根据商品类目、卖点和用户补充要求，输出 3 套差异化营销文案方案：

方案类型：
1. 卖点直述型：理性陈述卖点，突出功能参数与品质
2. 场景种草型：情感化场景叙事，引发共鸣与向往
3. 促销转化型：强调优惠/限时/性价比，促进下单

每套方案包含：
- title：短标题（15 字以内）
- main_copy：主图文案（1~2 句）
- detail_copy：详情页文案（2~3 句，一段）

{compliance_rules}

输出 JSON 格式：
{"plans": [{"type": "卖点直述型", "title": "...", "main_copy": "...", "detail_copy": "..."}, {"type": "场景种草型", ...}, {"type": "促销转化型", ...}]}

只输出 JSON，不要解释。"""


async def generate_copywriting(
    category: str,
    selling_points: list[dict] | None = None,
    user_hint: str = "",
    hotspots: list[dict] | None = None,
) -> dict:
    """生成 3 套营销文案方案（合规规则已注入 system prompt）。

    Args:
        category: 商品类目
        selling_points: 结构化卖点列表 [{point, visual_concept}]
        user_hint: 用户补充要求
        hotspots: 临近热点列表 [{name, hint, type, days_until}]，注入文案倾向

    Returns:
        {"plans": [{"type", "title", "main_copy", "detail_copy"}, ...]}
    """
    from app.services.compliance import compliance_rules_text
    from app.services.hot_calendar import hotspot_hint_text

    points = selling_points or []
    _ensure_llm_credentials()

    points_text = "；".join(
        f"{p.get('point', '')}（{p.get('visual_concept', '')}）" if p.get("visual_concept") else p.get("point", "")
        for p in points
    )
    hotspot_text = hotspot_hint_text(hotspots or [])
    user_content = (
        f"商品类目：{category or '未知'}\n"
        f"商品卖点：{points_text or '无'}\n"
        f"用户要求：{user_hint or '无'}"
    )
    if hotspot_text:
        user_content += f"\n临近热点（可融入文案场景）：{hotspot_text}"

    system_prompt = COPYWRITING_PROMPT.format(compliance_rules=compliance_rules_text())
    raw = await _call_llm(system_prompt, user_content)
    result = _parse_json(raw)
    plans = result.get("plans", [])
    normalized = []
    for plan in plans:
        normalized.append(
            {
                "type": (plan.get("type") or "").strip(),
                "title": (plan.get("title") or "").strip(),
                "main_copy": (plan.get("main_copy") or "").strip(),
                "detail_copy": (plan.get("detail_copy") or "").strip(),
            }
        )
    return {"plans": normalized}
