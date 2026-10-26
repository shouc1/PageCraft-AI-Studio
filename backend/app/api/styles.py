"""风格库管理路由（需求 v2 F-M3 风格库用户可感知层）。

风格数据源头是 app/kb/ 风格模板 Markdown（RAG 索引来源），本路由提供：
- GET  /api/styles            全量列表（可选 query 触发 RAG 推荐排序，推荐前 N 置顶）
- PUT  /api/styles/{name}     字段级编辑（写回源文件 + 后台重建索引）

会话工作区的风格推荐即走 GET /api/styles?query=...（见 SessionWorkspace）。
"""

from fastapi import APIRouter, HTTPException, Query

from app.models.style import (
    StyleEntry,
    StyleListResponse,
    StyleUpdateRequest,
    StyleUpdateResponse,
)
from app.services import styles as style_service
from app.logger import logger

router = APIRouter(prefix="/api/styles", tags=["styles"])


@router.get("", response_model=StyleListResponse)
async def list_styles(
    query: str = Query("", description="商品描述/类目/风格关键词；传入时 RAG 推荐前 top_k 置顶"),
    top_k: int = Query(3, ge=1, le=10, description="推荐条数"),
):
    """风格库全量列表。

    不传 query：按 kb 文件解析顺序返回（管理页用）。
    传 query：RAG 混合检索推荐前 top_k 置顶并标 recommended=True（风格选择器用）。
    """
    if query:
        ranked, rag_enabled = await style_service.recommend_and_rank(query, top_k)
        styles = [StyleEntry(**e) for e in ranked]
        logger.info("风格推荐：query=%s，top_k=%d，RAG=%s，共 %d 条",
                    query, top_k, rag_enabled, len(styles))
    else:
        entries = style_service.list_style_entries()
        rag_enabled = False
        styles = [StyleEntry(**e) for e in entries]
        logger.info("风格列表：共 %d 条", len(styles))

    return StyleListResponse(total=len(styles), rag_enabled=rag_enabled, styles=styles)


@router.put("/{name}", response_model=StyleUpdateResponse)
async def update_style(name: str, body: StyleUpdateRequest):
    """编辑风格条目（字段级更新，风格名不可改）。

    写回 app/kb/ 源文件后自动后台重建 RAG 索引（重建期间列表接口实时读文件，
    编辑结果立即可见；推荐检索在重建完成后生效）。
    """
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="至少提供一个更新字段")

    try:
        updated = await style_service.update_style_entry(name, updates)
    except LookupError:
        raise HTTPException(status_code=404, detail=f"风格不存在：{name}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return StyleUpdateResponse(status="ok", style=StyleEntry(**updated))
