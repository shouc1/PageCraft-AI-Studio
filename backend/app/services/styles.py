"""风格库服务：解析 kb 风格模板 → 结构化条目；字段级编辑写回；RAG 推荐排序。

数据来源为 app/kb/ 下 category=style_template 的 Markdown 文件（见 rag.CATEGORY_MAP）。
文件内按 --- 分隔风格条目，条目格式：

    # 风格：{名称}
    - 适用商品：...
    - 配色：...
    - 元素：...
    - 光线：...
    - 背景：...
    - 构图：...
    - prompt 模板：...
    - 负面提示：...

编辑流程：定位条目所在文件 → 块内字段行替换（缺失字段追加）→ 临时文件原子写回
→ 后台任务重建 RAG 索引（防重入 + pending 补跑，避免并发写丢失变更）。
"""

import asyncio
import os
import re

from app.config import BASE_DIR
from app.logger import logger

KB_DIR = BASE_DIR / "app" / "kb"

# API 字段名 ↔ kb 文件中文行前缀
FIELD_MAP: dict[str, str] = {
    "products": "适用商品",
    "colors": "配色",
    "elements": "元素",
    "lighting": "光线",
    "background": "背景",
    "composition": "构图",
    "prompt_template": "prompt 模板",
    "negative_prompt": "负面提示",
}

_STYLE_HEADER_RE = re.compile(r"^#\s*风格[：:]\s*(.+?)\s*$")
_FIELD_LINE_RE = re.compile(r"^-\s*([^：:\n]+?)\s*[：:]\s*(.*)$")

# 并发写保护（API 内）；重建任务防重入
_write_lock = asyncio.Lock()
_rebuild_task: asyncio.Task | None = None
_rebuild_pending = False


# ─── 解析 ──────────────────────────────────────────────────

def _style_files() -> list:
    """返回全部 style_template 类别的 kb 文件（按文件名排序，保证列表顺序稳定）。"""
    from app.services.rag import CATEGORY_MAP

    return [
        f for f in sorted(KB_DIR.glob("*.md"))
        if CATEGORY_MAP.get(f.name) == "style_template"
    ]


def _parse_block(block: str, source: str) -> dict | None:
    """解析单个风格块 → 条目 dict；非风格块（无 # 风格：标题）返回 None。"""
    lines = block.split("\n")
    m = _STYLE_HEADER_RE.match(lines[0].strip()) if lines else None
    if not m:
        return None

    entry = {
        "name": m.group(1).strip(),
        "source": source,
        "products": "",
        "colors": "",
        "elements": "",
        "lighting": "",
        "background": "",
        "composition": "",
        "prompt_template": "",
        "negative_prompt": "",
    }
    # 中文行前缀 → API 字段名
    cn_to_field = {cn: field for field, cn in FIELD_MAP.items()}
    for line in lines[1:]:
        fm = _FIELD_LINE_RE.match(line.strip())
        if fm and fm.group(1) in cn_to_field:
            entry[cn_to_field[fm.group(1)]] = fm.group(2).strip()
    return entry


def list_style_entries() -> list[dict]:
    """解析全部风格条目（实时读文件，不走索引，编辑后立即可见）。"""
    entries: list[dict] = []
    for md_file in _style_files():
        content = md_file.read_text(encoding="utf-8")
        for block in content.split("---"):
            block = block.strip()
            if not block:
                continue
            entry = _parse_block(block, md_file.name)
            if entry:
                entries.append(entry)
    return entries


def get_style_entry(name: str) -> dict | None:
    """按风格名查询单个条目。"""
    for entry in list_style_entries():
        if entry["name"] == name:
            return entry
    return None


# ─── 编辑写回 ──────────────────────────────────────────────

def _apply_updates(block: str, updates: dict[str, str]) -> str:
    """把字段更新应用到风格块文本：已有字段行替换，缺失字段追加到块尾。"""
    for field, value in updates.items():
        cn = FIELD_MAP[field]
        pattern = re.compile(
            r"^-\s*" + re.escape(cn) + r"\s*[：:]\s*.*$", re.MULTILINE
        )
        if pattern.search(block):
            # 用 lambda 避免替换值中的反斜杠被解释
            block = pattern.sub(lambda _: f"- {cn}：{value}", block, count=1)
        else:
            block = block.rstrip("\n") + f"\n- {cn}：{value}"
    return block


def _validate_values(updates: dict[str, str]) -> None:
    """校验更新值：不得包含换行或 ---（防止破坏 kb 文件分隔结构）。"""
    for field, value in updates.items():
        if "\n" in value or "---" in value:
            raise ValueError(f"字段 {field} 的值不允许包含换行或 '---' 分隔符")
        if field == "prompt_template" and not value:
            raise ValueError("prompt 模板不允许为空")


def _schedule_rebuild() -> None:
    """调度 RAG 索引后台重建。

    防重入：已有重建任务在跑时不重复启动，仅标记 pending，
    worker 循环结束前补跑一轮，保证重建期间的写回变更不丢失。
    """
    global _rebuild_task, _rebuild_pending
    _rebuild_pending = True
    if _rebuild_task is None or _rebuild_task.done():
        _rebuild_task = asyncio.create_task(_rebuild_worker())


async def _rebuild_worker() -> None:
    """后台重建知识库索引（编辑写回后调用）。"""
    global _rebuild_pending
    while _rebuild_pending:
        _rebuild_pending = False
        try:
            from app.services.rag import rebuild_knowledge_base, clear_cache

            clear_cache()
            stats = await rebuild_knowledge_base()
            logger.info(
                "风格编辑后知识库已重建：%s chunks", stats.get("chunk_count")
            )
        except Exception as e:
            logger.error("风格编辑后知识库重建失败：%s", e)


async def update_style_entry(name: str, updates: dict[str, str]) -> dict:
    """编辑风格条目：定位 → 字段级替换 → 原子写回 → 调度索引重建。

    Raises:
        ValueError: 值非法（含分隔符 / prompt 模板清空）
        LookupError: 风格不存在
    """
    updates = {k: v.strip() for k, v in updates.items()}
    _validate_values(updates)

    async with _write_lock:
        for md_file in _style_files():
            content = md_file.read_text(encoding="utf-8")
            blocks = [b.strip() for b in content.split("---")]
            for i, block in enumerate(blocks):
                lines = block.split("\n")
                m = _STYLE_HEADER_RE.match(lines[0].strip()) if lines else None
                if not m or m.group(1).strip() != name:
                    continue

                blocks[i] = _apply_updates(block, updates)
                new_content = "\n\n---\n\n".join(blocks) + "\n"
                tmp = md_file.with_suffix(".md.tmp")
                tmp.write_text(new_content, encoding="utf-8")
                os.replace(tmp, md_file)

                logger.info(
                    "风格已更新：%s（%s，字段：%s）",
                    name, md_file.name, ", ".join(updates.keys()),
                )
                _schedule_rebuild()
                updated = get_style_entry(name)
                if updated is None:  # 理论不可达（刚写回），防御性兜底
                    raise LookupError(f"风格不存在：{name}")
                return updated

    raise LookupError(f"风格不存在：{name}")


# ─── 推荐排序（F-M3）───────────────────────────────────────

async def recommend_and_rank(query: str, top_k: int = 3) -> tuple[list[dict], bool]:
    """全量风格 + 推荐排序。

    优先走 RAG 混合检索（style_template 类目），从命中 chunk 提取风格名；
    RAG 不可用或无命中时降级为关键词匹配（风格名 / 适用商品包含）。
    返回 (排序后条目列表, rag_enabled)；推荐条目置顶并标记 recommended=True。
    """
    entries = list_style_entries()
    rag_enabled = False
    recommended_names: list[str] = []

    if query:
        from app.services.rag import retrieve_knowledge, is_available

        if is_available():
            rag_enabled = True
            # 多取一倍候选，去重后截断 top_k
            hints = await retrieve_knowledge(
                query, top_k=max(top_k * 2, 6), category="style_template"
            )
            for hint in hints:
                m = _STYLE_HEADER_RE.match(hint.split("\n", 1)[0].strip())
                if m:
                    style_name = m.group(1).strip()
                    if style_name not in recommended_names:
                        recommended_names.append(style_name)

        if not recommended_names:
            # 降级：关键词包含匹配（RAG 不可用或检索无命中）
            for entry in entries:
                if query in entry["name"] or query in entry["products"]:
                    recommended_names.append(entry["name"])
                if len(recommended_names) >= top_k:
                    break

    top = recommended_names[:top_k]
    order = {n: i for i, n in enumerate(top)}
    for entry in entries:
        entry["recommended"] = entry["name"] in order
    # 推荐按命中顺序置顶，其余保持文件解析顺序（sorted 稳定）
    ranked = sorted(
        entries, key=lambda e: (0, order[e["name"]]) if e["name"] in order else (1, 0)
    )
    return ranked, rag_enabled
