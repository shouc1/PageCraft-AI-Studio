"""任务数据模型。"""

from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskCreate(BaseModel):
    """创建任务的请求体。"""
    user_prompt: str = Field(..., description="用户的一句话需求")
    workflow: Optional[str] = Field("auto", description="auto / image2image / text2image")
    input_image: Optional[str] = Field(None, description="上传的原图文件名")
    session_id: Optional[str] = Field(None, description="归属商品会话")
    images: list[str] = Field(default_factory=list, description="多参考图文件名列表（1~6 张）")
    kind: Optional[str] = Field("single", description="single / main_cover / main_image")
    strength: Optional[float] = Field(None, description="i2i 重绘强度（0.1~1.0）")
    size: Optional[str] = Field(None, description="生图尺寸，如 1024x1024")


class TaskResponse(BaseModel):
    """任务详情响应。"""
    id: str
    user_prompt: str
    workflow: str
    status: str
    progress: int
    input_image: Optional[str] = None
    result_image: Optional[str] = None
    expanded_prompt: Optional[str] = None
    error_message: Optional[str] = None
    session_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    kind: str = "single"
    image_index: Optional[int] = None
    sku: Optional[str] = None
    consistency: Optional[dict] = None
    created_at: str
    updated_at: str


class TaskListItem(BaseModel):
    """任务列表项（精简）。"""
    id: str
    user_prompt: str
    workflow: str
    status: str
    progress: int
    result_image: Optional[str] = None
    session_id: Optional[str] = None
    kind: str = "single"
    created_at: str


class TaskEventResponse(BaseModel):
    """任务时间线事件响应。"""
    id: str
    task_id: str
    stage: str
    message: str
    progress: int
    metadata: dict = Field(default_factory=dict)
    timestamp: str


class ConfirmBody(BaseModel):
    """用户确认 prompt 的请求体。"""
    prompt: str = Field(..., description="用户确认或修改后的 prompt")


# ─── 商品会话模型（需求 v2 §6.4）─────────────────────────

# 可识别的 5 个类目（与 kb/商品类型-*.md 一致）
CATEGORY_NAMES = ["家居家电", "数码电子", "服装鞋包", "美妆护肤", "食品饮料"]


class SellingPoint(BaseModel):
    """结构化卖点（三个模块共享、可编辑的资产）。"""
    point: str = Field(..., description="卖点名称")
    visual_concept: str = Field("", description="卖点视觉化建议")


class SessionCreate(BaseModel):
    """创建商品会话的请求体。"""
    name: str = Field("", description="商品名（用户填或 LLM 生成）")
    images: list[str] = Field(default_factory=list, description="商品图文件名列表（1~6 张）")
    user_hint: str = Field("", description="用户补充提示词")


class SessionUpdate(BaseModel):
    """更新会话资产（类目/卖点/风格/名称）。"""
    name: Optional[str] = None
    category: Optional[str] = None
    selling_points: Optional[list[SellingPoint]] = None
    style: Optional[str] = None
    images: Optional[list[str]] = None


class SessionResponse(BaseModel):
    """会话详情响应。"""
    id: str
    name: str
    category: str
    images: list[str]
    selling_points: list[SellingPoint]
    style: str
    status: str
    created_at: str
    updated_at: str


class CategoryResult(BaseModel):
    """类目识别结果。"""
    category: str
    confidence: float
    candidates: list[dict] = Field(default_factory=list, description="候选类目及置信度")
    need_confirm: bool = Field(False, description="低置信度时需用户确认")


class SellingPointsResult(BaseModel):
    """卖点提取结果。"""
    category: str
    selling_points: list[SellingPoint]


class GenerateImagesRequest(BaseModel):
    """批量生图请求（主图 4 张 / 每个 prompt 对应一张）。"""
    prompts: list[str] = Field(..., description="每张图的 prompt，长度即张数")
    kind: str = Field("main_image", description="main_image / detail_image")
    workflow: Optional[str] = Field(None, description="image2image / text2image，默认按参考图推断")
    platform: Optional[str] = Field(None, description="目标平台 taobao/jd/pdd/douyin，决定主图尺寸")
    skus: list[str] = Field(default_factory=list, description="SKU 变体名列表，非空则按变体批量生成")


class HintRequest(BaseModel):
    """识别 / 提取类辅助请求：用户补充提示词。"""
    user_hint: str = Field("", description="用户补充提示词")


# ─── P1：详情页结构规划（F-D1）──────────────────────────

class DetailSlot(BaseModel):
    """详情页单张结构定位。"""
    index: int
    slot: str = Field(..., description="定位名称，如 场景图 / 参数特写")
    desc: str = Field("", description="定位说明")
    prompt_hint: str = Field("", description="生图提示骨架")


class DetailPlanResult(BaseModel):
    """详情页结构规划结果。"""
    category: str
    slots: list[DetailSlot]


# ─── P1：营销文案（F-C1 / F-C2）────────────────────────

class CopyIssue(BaseModel):
    """文案合规违规项。"""
    field: str = Field(..., description="title / main_copy / detail_copy")
    word: str
    suggestion: str
    count: int = 1


class CopywritingPlan(BaseModel):
    """单套文案方案（含合规校验结果）。"""
    type: str
    title: str
    main_copy: str
    detail_copy: str
    issues: list[CopyIssue] = Field(default_factory=list)


class CopywritingResult(BaseModel):
    """营销文案生成结果。"""
    category: str
    plans: list[CopywritingPlan]
    hotspots: list[dict] = Field(default_factory=list, description="本次结合的热点")
