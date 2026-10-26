"""风格库模型（需求 v2 F-M3 风格库用户可感知层）。

风格数据源头是 app/kb/ 下的风格模板 Markdown（RAG 索引来源），
本模块定义其结构化表示与 API 请求/响应体。
"""

from pydantic import BaseModel, Field


class StyleEntry(BaseModel):
    """风格条目（kb 风格模板块的结构化表示）。"""

    name: str = Field(..., description="风格名（条目标识，不可编辑）")
    source: str = Field(..., description="来源 kb 文件名")
    products: str = Field("", description="适用商品")
    colors: str = Field("", description="配色")
    elements: str = Field("", description="元素")
    lighting: str = Field("", description="光线")
    background: str = Field("", description="背景")
    composition: str = Field("", description="构图")
    prompt_template: str = Field("", description="prompt 模板")
    negative_prompt: str = Field("", description="负面提示")
    recommended: bool = Field(False, description="是否 RAG 推荐前 N（仅推荐接口标记）")


class StyleListResponse(BaseModel):
    """风格列表响应（推荐排序结果）。"""

    total: int = Field(..., description="风格总数")
    rag_enabled: bool = Field(..., description="RAG 检索是否可用（不可用时为关键词降级匹配）")
    styles: list[StyleEntry] = Field(default_factory=list, description="风格条目（推荐置顶）")


class StyleUpdateRequest(BaseModel):
    """风格编辑请求（字段级更新，全部可选；风格名不可修改）。"""

    products: str | None = Field(None, description="适用商品")
    colors: str | None = Field(None, description="配色")
    elements: str | None = Field(None, description="元素")
    lighting: str | None = Field(None, description="光线")
    background: str | None = Field(None, description="背景")
    composition: str | None = Field(None, description="构图")
    prompt_template: str | None = Field(None, description="prompt 模板（不允许清空）")
    negative_prompt: str | None = Field(None, description="负面提示")


class StyleUpdateResponse(BaseModel):
    """风格编辑响应。"""

    status: str = Field("ok", description="操作状态")
    style: StyleEntry = Field(..., description="更新后的风格条目")
    index_rebuild: str = Field("scheduled", description="索引重建状态（写回后自动后台重建）")
