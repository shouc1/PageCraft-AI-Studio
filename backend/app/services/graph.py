"""LangGraph 三专家流水线编排。

用 LangGraph 的 StateGraph 替代手写 for 循环，实现：
  商品分析 → RAG 检索 → 视觉设计 → 质量评审 →（条件分支）
                                                  ├─ 通过 → 结束
                                                  └─ 不通过 → 回视觉设计（重试）
"""

from typing import TypedDict, Any, Callable, Awaitable
import time

from langgraph.graph import StateGraph, END, START

from app.services.llm import analyze_product, generate_prompt, review_prompt
from app.logger import logger

ProgressCallback = Callable[[str, str, dict | None], Awaitable[None]]
MAX_ATTEMPTS = 2

# ─── 节点耗时统计（供 /api/metrics 查询）─────────────────
_node_stats: dict[str, list[float]] = {}  # node_name -> [ durations in ms ]
_STATS_MAX = 100  # 每个节点只保留最近 100 次耗时


def _record_node_time(name: str, duration_ms: float) -> None:
    """记录单次节点执行耗时。"""
    if name not in _node_stats:
        _node_stats[name] = []
    _node_stats[name].append(duration_ms)
    if len(_node_stats[name]) > _STATS_MAX:
        _node_stats[name] = _node_stats[name][-_STATS_MAX:]


def get_node_stats() -> dict:
    """返回各节点耗时统计（供 /api/metrics 调用）。"""
    result = {}
    for name, durations in _node_stats.items():
        result[name] = {
            "count": len(durations),
            "avg_ms": round(sum(durations) / len(durations)) if durations else 0,
            "max_ms": round(max(durations)) if durations else 0,
            "last_ms": round(durations[-1]) if durations else 0,
        }
    return result


# ─── State 定义 ────────────────────────────────────────────
class AgentState(TypedDict, total=False):
    """LangGraph 全局状态，在节点间传递。"""
    user_prompt: str               # 用户输入
    is_image_to_image: bool        # 是否图生图
    analysis: dict                 # 专家1输出
    compliance_knowledge: list[str]  # 专家1用的合规规则知识
    visual_knowledge: list[str]    # 专家2用的视觉知识（词典+风格+示例+商品类型）
    review_knowledge: list[str]    # 专家3用的 SOP + 平台规范知识
    prompt: dict                   # 专家2输出 {positive_prompt, negative_prompt}
    review: dict                   # 专家3输出 {passed, score, issues, suggestions}
    feedback: str                  # 评审反馈给专家2
    attempt: int                   # 当前尝试次数
    final_prompt: str              # 最终输出
    on_progress: Any               # 进度回调（不参与序列化）


# ─── 节点函数 ──────────────────────────────────────────────

async def analyze_node(state: AgentState) -> dict:
    """节点 1：专家1 商品分析师（检索 compliance 合规规则）。"""
    on_progress = state.get("on_progress")
    if on_progress:
        await on_progress("analyzing", "商品分析中...")
    start = time.time()

    # 分专家检索：专家1 查合规规则
    compliance_knowledge: list[str] = []
    from app.services.rag import retrieve_knowledge, is_available
    if is_available():
        # 用用户输入检索对应品类的合规规则
        compliance_knowledge = await retrieve_knowledge(
            state["user_prompt"], top_k=2, category="compliance"
        )

    analysis = await analyze_product(state["user_prompt"], knowledge=compliance_knowledge)
    _record_node_time("analyze", (time.time() - start) * 1000)
    logger.info("节点 analyze 耗时 %.2fs（合规知识 %d 条）", time.time() - start, len(compliance_knowledge))
    return {"analysis": analysis, "compliance_knowledge": compliance_knowledge}


async def retrieve_node(state: AgentState) -> dict:
    """节点 2：RAG 知识检索（为专家2检索视觉知识，为专家3检索评审知识）。"""
    on_progress = state.get("on_progress")
    if on_progress:
        await on_progress("retrieving", "检索风格知识库...")
    start = time.time()
    from app.services.rag import retrieve_knowledge, is_available
    visual_knowledge: list[str] = []
    review_knowledge: list[str] = []
    if is_available():
        analysis = state["analysis"]
        product_type = analysis.get("product_type", "")
        visual_keywords = analysis.get("visual_keywords", [])
        usage_scenario = analysis.get("usage_scenario", "")

        # 专家2 查：卖点视觉化词典 + 风格模板 + prompt示例 + 商品类型知识
        visual_query = f"{product_type} {' '.join(visual_keywords)} {usage_scenario}"
        visual_knowledge = await retrieve_knowledge(
            visual_query,
            top_k=4,
            category=["visual_dict", "style_template", "prompt_example", "product_type"],
        )

        # 专家3 查：主图 SOP + 平台规范
        review_query = f"{product_type} {usage_scenario} 评审规范"
        review_knowledge = await retrieve_knowledge(
            review_query, top_k=2, category=["sop", "platform_spec"]
        )
        if on_progress:
            await on_progress(
                "retrieving",
                "知识库检索完成",
                {
                    "visual_matches": [item[:120] for item in visual_knowledge],
                    "review_matches": [item[:120] for item in review_knowledge],
                },
            )

    _record_node_time("retrieve", (time.time() - start) * 1000)
    logger.info("节点 retrieve 耗时 %.2fs（视觉知识 %d 条，评审知识 %d 条）",
                time.time() - start, len(visual_knowledge), len(review_knowledge))
    return {"visual_knowledge": visual_knowledge, "review_knowledge": review_knowledge}


async def design_node(state: AgentState) -> dict:
    """节点 3：专家2 视觉设计师。"""
    on_progress = state.get("on_progress")
    attempt = state.get("attempt", 0)
    attempt_label = f"（第 {attempt + 1} 次）" if attempt > 0 else ""
    if on_progress:
        await on_progress("designing", f"视觉设计中{attempt_label}...")
    start = time.time()
    prompt = await generate_prompt(
        state["analysis"],
        state.get("feedback", ""),
        state.get("visual_knowledge", []),
        is_image_to_image=state.get("is_image_to_image", False),
    )
    _record_node_time("design", (time.time() - start) * 1000)
    logger.info("节点 design 耗时 %.2fs", time.time() - start)
    return {"prompt": prompt, "attempt": attempt + 1}


async def review_node(state: AgentState) -> dict:
    """节点 4：专家3 质量评审员（使用 SOP + 平台规范知识评审）。"""
    on_progress = state.get("on_progress")
    if on_progress:
        await on_progress("reviewing", "质量评审中...")
    start = time.time()
    review = await review_prompt(
        state["prompt"],
        state["analysis"],
        knowledge=state.get("review_knowledge", []),
    )
    # 评审不通过时，准备反馈给专家2
    feedback = ""
    if not review.get("passed", False):
        feedback = review.get("suggestions", "") or "; ".join(review.get("issues", []))
    _record_node_time("review", (time.time() - start) * 1000)
    logger.info("节点 review 耗时 %.2fs", time.time() - start)
    return {"review": review, "feedback": feedback}


def should_retry(state: AgentState) -> str:
    """条件边路由函数：决定评审后走哪条边。"""
    if state["review"].get("passed", False):
        return "end"
    if state.get("attempt", 0) >= MAX_ATTEMPTS:
        return "end"
    return "retry"


def merge_negative_into_positive(positive: str, negative: str) -> str:
    """把负面提示转为否定句拼到正向 prompt 末尾。

    即梦 API 请求体没有 negative_prompt 字段（已查证官方文档），
    依赖 Seedream 语义理解以「画面中避免出现：…」形式生效。
    """
    negative = (negative or "").strip().rstrip("。；;.,， ")
    if not negative:
        return positive
    return f"{positive.rstrip()}\n画面中避免出现：{negative}。"


async def finalize_node(state: AgentState) -> dict:
    """终止节点：提取最终 prompt，并将负面提示以否定句并入。"""
    prompt = state["prompt"]
    final_prompt = merge_negative_into_positive(
        prompt.get("positive_prompt", ""),
        prompt.get("negative_prompt", ""),
    )
    if final_prompt != prompt.get("positive_prompt", ""):
        logger.info("负面提示已并入正向 prompt（否定句形式）")
    return {"final_prompt": final_prompt}


# ─── 构建图 ────────────────────────────────────────────────

def build_graph():
    """构建并编译 LangGraph 图。

    图结构：
        START → analyze → retrieve → design → review → (条件)
                                                      ├─ end   → finalize → END
                                                      └─ retry → design（循环）
    """
    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("analyze", analyze_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("design", design_node)
    graph.add_node("review", review_node)
    graph.add_node("finalize", finalize_node)

    # 添加固定边
    graph.add_edge(START, "analyze")
    graph.add_edge("analyze", "retrieve")
    graph.add_edge("retrieve", "design")
    graph.add_edge("design", "review")

    # 条件边：review 之后根据 should_retry 结果决定走向
    graph.add_conditional_edges(
        "review",
        should_retry,
        {
            "end": "finalize",
            "retry": "design",
        },
    )

    graph.add_edge("finalize", END)
    return graph.compile()


# 编译好的图实例（模块级单例）
app_graph = build_graph()


# ─── 对外接口 ──────────────────────────────────────────────

async def run_pipeline(
    user_prompt: str,
    on_progress: ProgressCallback | None = None,
    is_image_to_image: bool = False,
) -> str:
    """运行 LangGraph 三专家流水线，返回最终的 positive_prompt。"""
    initial_state: AgentState = {
        "user_prompt": user_prompt,
        "is_image_to_image": is_image_to_image,
        "analysis": {},
        "compliance_knowledge": [],
        "visual_knowledge": [],
        "review_knowledge": [],
        "prompt": {},
        "review": {},
        "feedback": "",
        "attempt": 0,
        "final_prompt": "",
        "on_progress": on_progress,
    }
    result = await app_graph.ainvoke(initial_state)
    return result["final_prompt"]
