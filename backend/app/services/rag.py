"""RAG 检索：Chroma 向量库 + BM25 关键词检索（混合检索）+ 本地 embedding。

P0 优化：分类元数据（category）+ 分专家检索（按 category 过滤）
P1 优化：中文 embedding（BAAI/bge-small-zh-v1.5）+ 按 Markdown 标题切分 + 索引 hash 自动更新
P2 优化：混合检索（向量 + BM25，RRF 融合）+ 知识库管理 API（rebuild/stats）

知识库文件放在 app/kb/*.md，按 --- 分隔条目，每个文件按文件名映射到 category。
首次启动时构建向量索引 + BM25 索引，之后通过 hash 比对自动检测变更并重建。
"""

import os
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import asyncio
import hashlib
import json
import math
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from app.config import BASE_DIR
from app.logger import logger

KB_DIR = BASE_DIR / "app" / "kb"
CHROMA_DIR = BASE_DIR / "data" / "chroma"
META_FILE = CHROMA_DIR / ".kb_meta.json"

# ─── P0：知识库分类映射 ────────────────────────────────────
# 每个知识库文件映射到一个 category，用于分专家检索过滤
CATEGORY_MAP: dict[str, str] = {
    "电商合规规则.md": "compliance",
    "卖点视觉化词典.md": "visual_dict",
    "商品海报风格模板.md": "style_template",
    "风格模板-运动活力.md": "style_template",
    "风格模板-赛博朋克.md": "style_template",
    "风格模板-日系和风.md": "style_template",
    "风格模板-工业复古.md": "style_template",
    "风格模板-极简ins风.md": "style_template",
    "电商主图SOP.md": "sop",
    "电商主图规范.md": "platform_spec",
    "prompt示例.md": "prompt_example",
    "负面prompt示例.md": "negative_prompt",
    "即梦workflow说明.md": "workflow",
    "商品类型-食品饮料.md": "product_type",
    "商品类型-美妆护肤.md": "product_type",
    "商品类型-数码电子.md": "product_type",
    "商品类型-服装鞋包.md": "product_type",
    "商品类型-家居家电.md": "product_type",
}

# ─── P1：embedding 模型候选（按优先级尝试，首个可用的胜出）──
EMBEDDING_CANDIDATES = [
    # 中文 embedding，对中文知识库效果更好（512 维）
    ("BAAI/bge-small-zh-v1.5", "bge-small-zh-v1.5"),
    # 英文 embedding，兜底（384 维）
    ("all-MiniLM-L6-v2", "all-MiniLM-L6-v2"),
]

# 全局单例
_embedder = None
_collection = None
_available = True
_current_model: str | None = None  # 当前实际加载的模型名

# BM25 索引 + 全量 chunk 缓存（供关键词检索用）
_bm25_index: "_BM25 | None" = None
_all_chunks: list[dict] = []  # [{"id", "document", "category", "source"}]

# 检索缓存（LRU，最多 128 条）
_query_cache: OrderedDict[str, list[str]] = OrderedDict()
_CACHE_MAX = 128
_SIMILARITY_THRESHOLD = 1.0  # L2 距离阈值，小于此值视为相关


# ─── P2：BM25 关键词检索（纯 Python 实现，无外部依赖）─────

def _tokenize_zh(text: str) -> list[str]:
    """简易中文分词：jieba 可用则用 jieba，否则用字符 bigram + ASCII 词切分。"""
    try:
        import jieba
        return [t for t in jieba.cut(text) if t.strip()]
    except ImportError:
        # 兜底：CJK 字符 bigram + ASCII 词
        tokens: list[str] = []
        i = 0
        while i < len(text):
            ch = text[i]
            if "\u4e00" <= ch <= "\u9fff":
                if i + 1 < len(text) and "\u4e00" <= text[i + 1] <= "\u9fff":
                    tokens.append(text[i : i + 2])
                tokens.append(ch)
                i += 1
            elif ch.isalnum():
                j = i
                while j < len(text) and text[j].isalnum():
                    j += 1
                tokens.append(text[i:j].lower())
                i = j
            else:
                i += 1
        return tokens


class _BM25:
    """BM25 关键词检索索引（内存版）。"""

    def __init__(self, docs: list[list[str]]):
        self.docs = docs
        self.N = len(docs)
        self.avg_len = sum(len(d) for d in docs) / self.N if self.N else 1
        self.k1 = 1.5
        self.b = 0.75
        # 文档频率
        self.df: dict[str, int] = {}
        for doc in docs:
            for token in set(doc):
                self.df[token] = self.df.get(token, 0) + 1

    def score(self, query_tokens: list[str], doc_idx: int) -> float:
        doc = self.docs[doc_idx]
        doc_len = len(doc)
        # 词频
        tf: dict[str, int] = {}
        for token in doc:
            tf[token] = tf.get(token, 0) + 1
        score = 0.0
        for token in query_tokens:
            if token not in tf:
                continue
            idf = math.log(1 + (self.N - self.df.get(token, 0) + 0.5) / (self.df.get(token, 0) + 0.5))
            numerator = tf[token] * (self.k1 + 1)
            denominator = tf[token] + self.k1 * (1 - self.b + self.b * doc_len / self.avg_len)
            score += idf * numerator / denominator
        return score


# ─── 依赖检查 ──────────────────────────────────────────────

def _check_available() -> bool:
    global _available
    try:
        import chromadb  # noqa: F401
        from sentence_transformers import SentenceTransformer  # noqa: F401
        return True
    except ImportError:
        _available = False
        return False


# ─── P1：embedding 模型加载（按候选优先级）─────────────────

def _get_embedder():
    """按 EMBEDDING_CANDIDATES 顺序尝试加载首个可用的模型。"""
    global _embedder, _current_model
    if _embedder is not None:
        return _embedder

    from sentence_transformers import SentenceTransformer

    for model_name, dir_name in EMBEDDING_CANDIDATES:
        model_dir = BASE_DIR / "models" / dir_name
        try:
            if model_dir.exists():
                _embedder = SentenceTransformer(str(model_dir), device="cpu")
            else:
                # 尝试在线下载（HF_HUB_OFFLINE=1 时会跳过）
                _embedder = SentenceTransformer(model_name, device="cpu")
            _current_model = model_name
            logger.info("已加载 embedding 模型：%s", model_name)
            break
        except Exception as e:
            logger.warning("加载 embedding 模型 %s 失败，尝试下一个：%s", model_name, e)
            _embedder = None
            continue

    if _embedder is None:
        raise RuntimeError("所有 embedding 候选模型均加载失败")
    return _embedder


def _get_collection():
    global _collection
    if _collection is None:
        import chromadb
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = client.get_or_create_collection("style_knowledge")
    return _collection


# ─── P1：索引 hash 自动更新 ────────────────────────────────

def _compute_kb_hash() -> str:
    """计算所有知识库文件的 hash（文件名 + 内容 + 修改时间），用于检测变更。"""
    h = hashlib.md5()
    for md_file in sorted(KB_DIR.glob("*.md")):
        stat = md_file.stat()
        h.update(f"{md_file.name}|{stat.st_size}|{int(stat.st_mtime)}".encode("utf-8"))
    return h.hexdigest()


def _load_kb_meta() -> dict:
    """读取知识库元数据（记录上次构建时的模型名、hash、条目数）。"""
    if META_FILE.exists():
        try:
            return json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_kb_meta(model_name: str, kb_hash: str, chunk_count: int):
    META_FILE.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "model_name": model_name,
        "kb_hash": kb_hash,
        "chunk_count": chunk_count,
        "last_build": datetime.now().isoformat(),
    }
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── P1：按 Markdown 标题切分 ──────────────────────────────

def _split_by_heading(content: str) -> list[str]:
    """智能切分：先按 --- 分隔，再对超长块按 ## 标题二次切分，保留父标题上下文。"""
    # 第一层：按 --- 切分
    raw_chunks = [c.strip() for c in content.split("---") if c.strip()]

    result: list[str] = []
    for chunk in raw_chunks:
        # 提取一级标题（# 开头）作为上下文前缀
        first_line = chunk.split("\n", 1)[0] if chunk else ""
        parent_title = first_line if first_line.startswith("# ") else ""

        # 如果块较短（< 400 字符），直接保留
        if len(chunk) < 400:
            result.append(chunk)
            continue

        # 对长块按 ## 标题二次切分
        sections = re.split(r"^##\s+", chunk, flags=re.MULTILINE)
        if len(sections) <= 1:
            # 没有 ## 标题，保持原样
            result.append(chunk)
            continue

        # 第一段是不含 ## 的开头（通常是 # 一级标题 + 引言）
        header_part = sections[0].strip()
        if header_part and len(header_part) < 200:
            # 作为上下文前缀附加到每个子块
            for sec in sections[1:]:
                sec = sec.strip()
                if sec:
                    sub_chunk = f"{header_part}\n## {sec}" if not sec.startswith("##") else sec
                    result.append(sub_chunk)
        else:
            # 开头较长，单独保留
            if header_part:
                result.append(header_part)
            for sec in sections[1:]:
                sec = sec.strip()
                if sec:
                    result.append(f"## {sec}" if not sec.startswith("##") else sec)

    return result


# ─── 索引构建 ──────────────────────────────────────────────

def _build_index_sync():
    """构建向量索引 + BM25 索引（全量重建）。"""
    global _bm25_index, _all_chunks

    collection = _get_collection()
    embedder = _get_embedder()

    # 清空旧数据
    try:
        existing = collection.get()
        if existing and existing["ids"]:
            collection.delete(ids=existing["ids"])
    except Exception:
        pass

    _all_chunks = []
    bm25_docs: list[list[str]] = []
    total = 0

    for md_file in sorted(KB_DIR.glob("*.md")):
        category = CATEGORY_MAP.get(md_file.name, "other")
        content = md_file.read_text(encoding="utf-8")
        chunks = _split_by_heading(content)

        for i, chunk in enumerate(chunks):
            chunk_id = f"{md_file.stem}_{i}"
            embedding = embedder.encode(chunk).tolist()

            # 提取风格名（仅 style_template 类别，用于更精准检索）
            style_name = ""
            if category == "style_template":
                m = re.match(r"#\s*风格[：:]\s*(.+)", chunk.split("\n")[0] if chunk else "")
                if m:
                    style_name = m.group(1).strip()

            metadata = {
                "source": md_file.name,
                "category": category,
                "chunk_index": i,
            }
            if style_name:
                metadata["style_name"] = style_name

            collection.add(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[chunk],
                metadatas=[metadata],
            )

            _all_chunks.append({
                "id": chunk_id,
                "document": chunk,
                "category": category,
                "source": md_file.name,
            })
            bm25_docs.append(_tokenize_zh(chunk))
            total += 1

    # 构建 BM25 索引
    _bm25_index = _BM25(bm25_docs)

    # 保存元数据
    _save_kb_meta(_current_model or "unknown", _compute_kb_hash(), total)
    logger.info("知识库构建完成，共 %d 条（来自 %d 个文件，模型 %s）",
                total, len(list(KB_DIR.glob("*.md"))), _current_model)


def _init_knowledge_base_sync():
    """启动时调用：通过 hash + 模型名比对决定是否重建。"""
    if not _check_available():
        logger.warning("chromadb / sentence-transformers 未安装，跳过知识库构建")
        return

    collection = _get_collection()
    stored_meta = _load_kb_meta()
    current_hash = _compute_kb_hash()

    # 确定当前可用模型（不实际加载，仅检查目录）
    # 优先 bge-small-zh，其次 all-MiniLM
    preferred_model = EMBEDDING_CANDIDATES[0][0]
    for model_name, dir_name in EMBEDDING_CANDIDATES:
        if (BASE_DIR / "models" / dir_name).exists():
            preferred_model = model_name
            break

    need_rebuild = False
    reason = ""

    if collection.count() == 0:
        need_rebuild = True
        reason = "知识库为空"
    elif stored_meta.get("model_name") != preferred_model:
        need_rebuild = True
        reason = f"模型变更（{stored_meta.get('model_name')} → {preferred_model}）"
    elif stored_meta.get("kb_hash") != current_hash:
        need_rebuild = True
        reason = "知识库文件已变更"

    if need_rebuild:
        logger.info("重建知识库：%s", reason)
        _build_index_sync()
    else:
        # 加载已有 chunk 到内存（供 BM25 用）
        _load_existing_chunks_sync()
        logger.info("知识库已存在，共 %d 条，跳过构建", collection.count())


def _load_existing_chunks_sync():
    """从 Chroma 加载全量 chunk 到内存，构建 BM25 索引（不重建向量）。"""
    global _all_chunks, _bm25_index

    collection = _get_collection()
    data = collection.get()
    if not data or not data["ids"]:
        return

    _all_chunks = []
    bm25_docs: list[list[str]] = []
    for i, doc_id in enumerate(data["ids"]):
        doc = data["documents"][i]
        meta = data["metadatas"][i] if data["metadatas"] else {}
        _all_chunks.append({
            "id": doc_id,
            "document": doc,
            "category": meta.get("category", "other"),
            "source": meta.get("source", ""),
        })
        bm25_docs.append(_tokenize_zh(doc))

    _bm25_index = _BM25(bm25_docs)
    logger.info("BM25 索引已加载（%d 条 chunk）", len(_all_chunks))


async def init_knowledge_base():
    """异步版：启动时调用。"""
    await asyncio.to_thread(_init_knowledge_base_sync)


async def rebuild_knowledge_base() -> dict:
    """强制重建知识库（供 /api/kb/rebuild 调用）。"""
    await asyncio.to_thread(_build_index_sync)
    return get_kb_stats()


# ─── 混合检索（P2）────────────────────────────────────────

def _build_where_filter(category: str | list[str] | None) -> dict | None:
    """构建 Chroma where 过滤条件。"""
    if category is None:
        return None
    if isinstance(category, str):
        return {"category": category}
    if isinstance(category, list) and category:
        return {"category": {"$in": category}}
    return None


def _vector_search(query: str, top_k: int, category: str | list[str] | None) -> list[dict]:
    """向量检索（Chroma），返回 [{"document", "distance", "category"}]。"""
    collection = _get_collection()
    if collection.count() == 0:
        return []

    embedder = _get_embedder()
    query_embedding = embedder.encode(query).tolist()

    kwargs = {"query_embeddings": [query_embedding], "n_results": top_k}
    where = _build_where_filter(category)
    if where:
        kwargs["where"] = where

    results = collection.query(**kwargs)

    docs = results["documents"][0] if results["documents"] else []
    distances = results.get("distances", [[]])[0] if results.get("distances") else []
    metadatas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []

    output = []
    for i, doc in enumerate(docs):
        dist = distances[i] if i < len(distances) else 1.0
        meta = metadatas[i] if i < len(metadatas) else {}
        output.append({
            "document": doc,
            "distance": dist,
            "category": meta.get("category", "other"),
        })
    return output


def _bm25_search(query: str, top_k: int, category: str | list[str] | None) -> list[dict]:
    """BM25 关键词检索，返回 [{"document", "score", "category"}]。"""
    if _bm25_index is None or not _all_chunks:
        return []

    query_tokens = _tokenize_zh(query)
    if not query_tokens:
        return []

    # 允许的 category 集合
    allowed = None
    if category is not None:
        allowed = {category} if isinstance(category, str) else set(category)

    scored = []
    for idx, chunk in enumerate(_all_chunks):
        if allowed and chunk["category"] not in allowed:
            continue
        score = _bm25_index.score(query_tokens, idx)
        if score > 0:
            scored.append((score, idx))

    scored.sort(reverse=True)
    return [
        {"document": _all_chunks[idx]["document"], "score": score, "category": _all_chunks[idx]["category"]}
        for score, idx in scored[:top_k]
    ]


def _rrf_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    top_k: int,
    k: int = 60,
) -> list[str]:
    """Reciprocal Rank Fusion：融合两路检索结果，返回 top_k 文本列表。"""
    scores: dict[str, float] = {}

    for rank, item in enumerate(vector_results):
        doc = item["document"]
        scores[doc] = scores.get(doc, 0) + 1.0 / (k + rank + 1)

    for rank, item in enumerate(bm25_results):
        doc = item["document"]
        scores[doc] = scores.get(doc, 0) + 1.0 / (k + rank + 1)

    sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [doc for doc, _ in sorted_docs[:top_k]]


def _retrieve_sync(
    query: str,
    top_k: int = 3,
    category: str | list[str] | None = None,
) -> list[str]:
    """混合检索（向量 + BM25，RRF 融合），带 LRU 缓存 + 相似度阈值过滤。"""
    # 1. 缓存命中检查
    cat_key = category if isinstance(category, str) else "|".join(category) if category else "all"
    cache_key = f"{query}|{top_k}|{cat_key}"
    if cache_key in _query_cache:
        _query_cache.move_to_end(cache_key)
        logger.info("RAG 检索命中缓存: %s [category=%s]", query[:30], cat_key)
        return _query_cache[cache_key]

    if not _check_available():
        return []

    collection = _get_collection()
    if collection.count() == 0:
        return []

    # 2. 双路检索（各取 top_k * 2 候选）
    candidate_k = max(top_k * 2, 6)
    vector_results = _vector_search(query, candidate_k, category)
    bm25_results = _bm25_search(query, candidate_k, category)

    # 3. 向量结果相似度阈值过滤
    if vector_results:
        filtered = [r for r in vector_results if r["distance"] < _SIMILARITY_THRESHOLD]
        if filtered:
            vector_results = filtered

    # 4. RRF 融合
    if vector_results and bm25_results:
        docs = _rrf_fusion(vector_results, bm25_results, top_k)
    elif vector_results:
        docs = [r["document"] for r in vector_results[:top_k]]
    elif bm25_results:
        docs = [r["document"] for r in bm25_results[:top_k]]
    else:
        docs = []

    logger.info("RAG 混合检索 [category=%s]: 向量 %d 条 + BM25 %d 条 → 融合后 %d 条",
                cat_key, len(vector_results), len(bm25_results), len(docs))

    # 5. 写入缓存
    _query_cache[cache_key] = docs
    if len(_query_cache) > _CACHE_MAX:
        _query_cache.popitem(last=False)

    return docs


async def retrieve_knowledge(
    query: str,
    top_k: int = 3,
    category: str | list[str] | None = None,
) -> list[str]:
    """检索最相关的 top_k 条知识，返回文本列表。

    Args:
        query: 查询文本
        top_k: 返回条数
        category: 指定知识类别过滤，支持单个类别或类别列表：
            - compliance: 合规规则
            - visual_dict: 卖点视觉化词典
            - style_template: 风格模板
            - product_type: 商品类型知识
            - sop: 主图策划 SOP
            - platform_spec: 平台规范
            - prompt_example: prompt 示例
            - negative_prompt: 负面 prompt
    """
    return await asyncio.to_thread(_retrieve_sync, query, top_k, category)


# ─── 知识库管理 API（P2）───────────────────────────────────

def get_kb_stats() -> dict:
    """返回知识库统计信息（供 /api/kb/stats 调用）。"""
    meta = _load_kb_meta()
    file_count = len(list(KB_DIR.glob("*.md")))

    # 按 category 统计 chunk 数
    category_counts: dict[str, int] = {}
    for chunk in _all_chunks:
        cat = chunk["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    collection = _get_collection() if _check_available() else None
    chunk_count = collection.count() if collection else 0

    return {
        "file_count": file_count,
        "chunk_count": chunk_count,
        "model": _current_model or meta.get("model_name", "unknown"),
        "last_build": meta.get("last_build", ""),
        "categories": category_counts,
        "available": _check_available(),
    }


def is_available() -> bool:
    """RAG 是否可用（依赖已安装）。"""
    return _check_available()


def clear_cache() -> None:
    """清空检索缓存（知识库重建后调用）。"""
    _query_cache.clear()
    logger.info("RAG 检索缓存已清空")
