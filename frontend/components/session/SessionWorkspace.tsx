"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  Image,
  ImagePlus,
  LayoutList,
  Library,
  Loader2,
  Megaphone,
  Plus,
  Save,
  Sparkles,
  Tags,
  Trash2,
  Wand2,
} from "lucide-react";
import { AppHeader } from "@/components/layout/AppHeader";
import {
  categorizeSession,
  extractSellingPoints,
  getImageUrl,
  getSession,
  listStyles,
  updateSession,
  uploadImage,
  type CategoryResult,
  type CopywritingResult,
  type SellingPoint,
  type Session,
  type StyleEntry,
} from "@/lib/api";
import { MainImageTab } from "./MainImageTab";
import { DetailTab } from "./DetailTab";
import { CopywritingTab } from "./CopywritingTab";

const CATEGORY_NAMES = ["家居家电", "数码电子", "服装鞋包", "美妆护肤", "食品饮料"];

type TabKey = "main" | "detail" | "copy";

const TABS: { key: TabKey; label: string; icon: typeof Image }[] = [
  { key: "main", label: "主图生成", icon: Image },
  { key: "detail", label: "详情页生成", icon: LayoutList },
  { key: "copy", label: "营销文案", icon: Megaphone },
];

export function SessionWorkspace({ sessionId }: { sessionId: string }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loadError, setLoadError] = useState("");
  const [tab, setTab] = useState<TabKey>("main");

  const [categoryResult, setCategoryResult] = useState<CategoryResult | null>(null);
  const [categorizing, setCategorizing] = useState(false);

  const [sellingPoints, setSellingPoints] = useState<SellingPoint[]>([]);
  const [extracting, setExtracting] = useState(false);

  const [styles, setStyles] = useState<StyleEntry[]>([]);
  const [stylesLoading, setStylesLoading] = useState(false);
  const [ragEnabled, setRagEnabled] = useState(true);
  const [style, setStyle] = useState("");

  const [promptHint, setPromptHint] = useState("");
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);

  // 文案模块产出，供详情页图文混排回填（保证三处文案一致）
  const [copyResult, setCopyResult] = useState<CopywritingResult | null>(null);

  // 加载会话 + 卖点 / 风格资产
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await getSession(sessionId);
        if (cancelled) return;
        setSession(s);
        setSellingPoints(s.selling_points);
        setStyle(s.style);
        refreshStyles(s.category, s.name);
      } catch (err) {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "加载会话失败");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // ─── 图片上传（1~6 张）────────────────────────────
  async function handleUploadFiles(files: FileList | null) {
    if (!files || files.length === 0 || !session) return;
    const slots = Math.max(0, 6 - session.images.length);
    const list = Array.from(files).slice(0, slots);
    if (list.length === 0) return;
    setUploading(true);
    try {
      const filenames: string[] = [];
      for (const file of list) {
        const res = await uploadImage(file);
        filenames.push(res.filename);
      }
      const updated = await updateSession(sessionId, {
        images: [...session.images, ...filenames],
      });
      setSession(updated);
    } catch (err) {
      alert(err instanceof Error ? err.message : "图片上传失败");
    } finally {
      setUploading(false);
    }
  }

  async function handleRemoveImage(index: number) {
    if (!session) return;
    const images = session.images.filter((_, i) => i !== index);
    setSession(await updateSession(sessionId, { images }));
  }

  // ─── 风格推荐（F-M3：类目 / 卖点变化后重取，RAG 推荐前 3 置顶）──
  async function refreshStyles(category: string, name: string) {
    const query = `${category} ${name}`.trim();
    setStylesLoading(true);
    try {
      const res = await listStyles(query);
      setStyles(res.styles);
      setRagEnabled(res.rag_enabled);
    } catch {
      // 推荐获取失败不阻断主流程，保留已有列表
    } finally {
      setStylesLoading(false);
    }
  }

  // ─── 类目识别（F-M1）────────────────────────────
  async function handleCategorize() {
    setCategorizing(true);
    setCategoryResult(null);
    try {
      const result = await categorizeSession(sessionId, promptHint);
      setCategoryResult(result);
      if (!result.need_confirm && result.category) {
        const updated = await getSession(sessionId);
        setSession(updated);
        refreshStyles(updated.category, updated.name);
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : "类目识别失败");
    } finally {
      setCategorizing(false);
    }
  }

  async function handleConfirmCategory(category: string) {
    const updated = await updateSession(sessionId, { category });
    setSession(updated);
    setCategoryResult(null);
    refreshStyles(updated.category, updated.name);
  }

  // ─── 卖点提取（F-M2）────────────────────────────
  async function handleExtractPoints() {
    setExtracting(true);
    try {
      const result = await extractSellingPoints(sessionId, promptHint);
      setSellingPoints(result.selling_points);
      setSession(await updateSession(sessionId, { selling_points: result.selling_points }));
    } catch (err) {
      alert(err instanceof Error ? err.message : "卖点提取失败");
    } finally {
      setExtracting(false);
    }
  }

  function updatePoint(index: number, field: keyof SellingPoint, value: string) {
    setSellingPoints((prev) =>
      prev.map((p, i) => (i === index ? { ...p, [field]: value } : p))
    );
  }

  function removePoint(index: number) {
    setSellingPoints((prev) => prev.filter((_, i) => i !== index));
  }

  function addPoint() {
    setSellingPoints((prev) => [...prev, { point: "", visual_concept: "" }]);
  }

  async function savePoints() {
    setBusy(true);
    try {
      const updated = await updateSession(sessionId, {
        selling_points: sellingPoints,
      });
      setSession(updated);
      // 卖点变化影响 RAG 推荐语义，保存后重取推荐
      refreshStyles(updated.category, updated.name);
    } catch (err) {
      alert(err instanceof Error ? err.message : "卖点保存失败");
    } finally {
      setBusy(false);
    }
  }

  // ─── 风格选择（F-M3）────────────────────────────
  async function handleSelectStyle(nextStyle: string) {
    setStyle(nextStyle);
    try {
      setSession(await updateSession(sessionId, { style: nextStyle }));
    } catch (err) {
      alert(err instanceof Error ? err.message : "风格保存失败");
    }
  }

  if (loadError) {
    return (
      <main className="min-h-screen bg-slate-50">
        <AppHeader />
        <div className="mx-auto max-w-lg p-10 text-center">
          <p className="text-sm text-red-600">{loadError}</p>
          <Link
            className="mt-4 inline-block text-sm text-blue-600 hover:underline"
            href="/"
          >
            返回会话列表
          </Link>
        </div>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="min-h-screen bg-slate-50">
        <AppHeader />
        <div className="flex items-center justify-center p-20">
          <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
        </div>
      </main>
    );
  }

  // 选中风格的详情（kb 结构化字段，选中即展开）
  const selectedStyle = styles.find((s) => s.name === style);

  return (
    <main className="min-h-screen bg-slate-50">
      <AppHeader />

      <div className="mx-auto max-w-7xl p-4 lg:p-6">
        {/* 会话头部 */}
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <input
              className="w-full max-w-sm rounded-lg border border-line bg-white px-3 py-2 text-base font-semibold text-ink outline-none focus:border-slate-400"
              value={session.name}
              onChange={(e) => setSession({ ...session, name: e.target.value })}
              onBlur={() => {
                if (session.name.trim()) {
                  updateSession(sessionId, { name: session.name.trim() }).catch(() => {});
                }
              }}
            />
            {session.category && (
              <span className="shrink-0 rounded bg-blue-100 px-2 py-1 text-xs font-medium text-blue-700">
                {session.category}
              </span>
            )}
            <span className="shrink-0 rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600">
              {session.status === "draft" ? "草稿" : session.status}
            </span>
          </div>
          <Link
            className="text-sm text-slate-500 hover:text-slate-700"
            href="/"
          >
            ← 返回会话列表
          </Link>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
          {/* ── 左栏：商品资产（三模块共享）── */}
          <aside className="flex min-h-0 flex-col gap-4">
            {/* 商品图上传 */}
            <section className="rounded-lg border border-line bg-panel p-4">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-ink">商品图</h2>
                <span className="text-xs text-slate-500">
                  {session.images.length}/6
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2">
                {session.images.map((img, i) => (
                  <div
                    className="group relative aspect-square overflow-hidden rounded-md border border-line bg-slate-100"
                    key={img}
                  >
                    <img
                      alt={`商品图 ${i + 1}`}
                      className="h-full w-full object-cover"
                      src={getImageUrl(img) || ""}
                    />
                    <button
                      className="absolute right-1 top-1 rounded bg-black/50 p-1 text-white opacity-0 transition group-hover:opacity-100"
                      onClick={() => handleRemoveImage(i)}
                      title="移除"
                      type="button"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
                {session.images.length < 6 && (
                  <label className="flex aspect-square cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-slate-300 bg-slate-50 text-slate-400 transition hover:border-slate-400 hover:text-slate-600">
                    {uploading ? (
                      <Loader2 className="h-5 w-5 animate-spin" />
                    ) : (
                      <>
                        <ImagePlus className="h-5 w-5" />
                        <span className="mt-1 text-xs">上传</span>
                      </>
                    )}
                    <input
                      accept="image/*"
                      className="hidden"
                      multiple
                      onChange={(e) => handleUploadFiles(e.target.files)}
                      type="file"
                    />
                  </label>
                )}
              </div>
              <p className="mt-2 text-xs text-slate-400">
                最多 6 张，多角度参考提升商品一致性
              </p>
            </section>

            {/* 类目识别 */}
            <section className="rounded-lg border border-line bg-panel p-4">
              <div className="mb-2 flex items-center gap-2">
                <Tags className="h-4 w-4 text-slate-500" />
                <h2 className="text-sm font-semibold text-ink">类目识别</h2>
              </div>
              <input
                className="mb-2 w-full rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-slate-400"
                onChange={(e) => setPromptHint(e.target.value)}
                placeholder="补充商品描述（可选）"
                value={promptHint}
              />
              <button
                className="flex h-9 w-full items-center justify-center gap-2 rounded-md bg-ink px-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:bg-slate-400"
                disabled={categorizing}
                onClick={handleCategorize}
                type="button"
              >
                {categorizing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                {categorizing ? "识别中..." : "识别类目"}
              </button>

              {categoryResult?.need_confirm && (
                <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3">
                  <p className="mb-2 text-xs text-slate-600">
                    置信度较低，请确认类目：
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {categoryResult.candidates.map((c) => (
                      <button
                        className="rounded-md border border-line bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                        key={c.category}
                        onClick={() => handleConfirmCategory(c.category)}
                        type="button"
                      >
                        {c.category}
                      </button>
                    ))}
                    {CATEGORY_NAMES.filter(
                      (c) => !categoryResult.candidates.some((x) => x.category === c)
                    ).map((c) => (
                      <button
                        className="rounded-md border border-line bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                        key={c}
                        onClick={() => handleConfirmCategory(c)}
                        type="button"
                      >
                        {c}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </section>

            {/* 卖点提取与编辑 */}
            <section className="rounded-lg border border-line bg-panel p-4">
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Wand2 className="h-4 w-4 text-slate-500" />
                  <h2 className="text-sm font-semibold text-ink">卖点资产</h2>
                </div>
                <button
                  className="flex items-center gap-1 text-xs text-blue-600 hover:underline"
                  disabled={extracting}
                  onClick={handleExtractPoints}
                  type="button"
                >
                  {extracting ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Sparkles className="h-3.5 w-3.5" />
                  )}
                  提取卖点
                </button>
              </div>

              <div className="space-y-2">
                {sellingPoints.map((p, i) => (
                  <div
                    className="space-y-1 rounded-md border border-line bg-white p-2"
                    key={i}
                  >
                    <div className="flex items-center gap-2">
                      <input
                        className="min-w-0 flex-1 rounded border border-line px-2 py-1 text-sm outline-none focus:border-slate-400"
                        onChange={(e) => updatePoint(i, "point", e.target.value)}
                        placeholder="卖点名称"
                        value={p.point}
                      />
                      <button
                        className="rounded p-1 text-slate-400 hover:text-red-600"
                        onClick={() => removePoint(i)}
                        title="删除"
                        type="button"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    <input
                      className="w-full rounded border border-line px-2 py-1 text-xs text-slate-600 outline-none focus:border-slate-400"
                      onChange={(e) => updatePoint(i, "visual_concept", e.target.value)}
                      placeholder="视觉化建议（可选）"
                      value={p.visual_concept}
                    />
                  </div>
                ))}
              </div>

              <div className="mt-2 flex items-center gap-2">
                <button
                  className="flex h-8 items-center gap-1 rounded-md border border-line bg-white px-2 text-xs text-slate-600 hover:bg-slate-50"
                  onClick={addPoint}
                  type="button"
                >
                  <Plus className="h-3.5 w-3.5" />
                  添加卖点
                </button>
                <button
                  className="ml-auto flex h-8 items-center gap-1 rounded-md bg-slate-900 px-3 text-xs font-medium text-white hover:bg-slate-700 disabled:bg-slate-400"
                  disabled={busy}
                  onClick={savePoints}
                  type="button"
                >
                  <Save className="h-3.5 w-3.5" />
                  保存卖点
                </button>
              </div>
            </section>

            {/* 风格选择（F-M3：RAG 推荐前 3 置顶，全量风格可选） */}
            <section className="rounded-lg border border-line bg-panel p-4">
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Library className="h-4 w-4 text-slate-500" />
                  <h2 className="text-sm font-semibold text-ink">风格</h2>
                  {stylesLoading && (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" />
                  )}
                </div>
                <Link
                  className="flex items-center gap-0.5 text-xs text-blue-600 hover:underline"
                  href="/styles"
                >
                  管理风格库
                  <ArrowUpRight className="h-3 w-3" />
                </Link>
              </div>
              <div className="flex flex-wrap gap-2">
                {styles.map((s) => (
                  <button
                    className={`relative rounded-md border px-3 py-1.5 text-sm transition ${
                      style === s.name
                        ? "border-ink bg-ink text-white"
                        : "border-line bg-white text-slate-700 hover:bg-slate-50"
                    }`}
                    key={s.name}
                    onClick={() => handleSelectStyle(s.name)}
                    title={
                      [
                        s.products && `适用：${s.products}`,
                        s.colors && `配色：${s.colors}`,
                      ]
                        .filter(Boolean)
                        .join("\n") || undefined
                    }
                    type="button"
                  >
                    {s.recommended && (
                      <span className="mr-1 text-xs text-amber-500">★</span>
                    )}
                    {s.name}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-xs text-slate-400">
                {ragEnabled
                  ? "★ 为 RAG 推荐风格（前 3）"
                  : "当前为关键词匹配推荐（RAG 未启用）"}
              </p>

              {/* 选中风格详情（点击选中即展开） */}
              {selectedStyle && (
                <div className="mt-2 rounded-md border border-line bg-slate-50 p-2.5 text-xs leading-5 text-slate-600">
                  {selectedStyle.products && (
                    <p>
                      <span className="text-slate-400">适用：</span>
                      {selectedStyle.products}
                    </p>
                  )}
                  {selectedStyle.colors && (
                    <p>
                      <span className="text-slate-400">配色：</span>
                      {selectedStyle.colors}
                    </p>
                  )}
                  {selectedStyle.prompt_template && (
                    <p className="mt-1 line-clamp-2 font-mono text-slate-500">
                      {selectedStyle.prompt_template}
                    </p>
                  )}
                </div>
              )}
            </section>
          </aside>

          {/* ── 右栏：三个工作视图 ── */}
          <section className="flex min-h-0 flex-col gap-4">
            <div className="flex gap-1 border-b border-line">
              {TABS.map((t) => {
                const Icon = t.icon;
                const active = tab === t.key;
                return (
                  <button
                    className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition ${
                      active
                        ? "border-ink text-ink"
                        : "border-transparent text-slate-500 hover:text-slate-700"
                    }`}
                    key={t.key}
                    onClick={() => setTab(t.key)}
                    type="button"
                  >
                    <Icon className="h-4 w-4" />
                    {t.label}
                  </button>
                );
              })}
            </div>

            <div className={tab === "main" ? "flex flex-col gap-4" : "hidden"}>
              <MainImageTab
                category={session.category}
                copywriting={copyResult}
                sellingPoints={sellingPoints}
                sessionId={sessionId}
                style={style}
                hasImages={session.images.length > 0}
              />
            </div>
            <div className={tab === "detail" ? "flex flex-col gap-4" : "hidden"}>
              <DetailTab
                category={session.category}
                copywriting={copyResult}
                sellingPoints={sellingPoints}
                sessionId={sessionId}
                style={style}
                hasImages={session.images.length > 0}
              />
            </div>
            <div className={tab === "copy" ? "flex flex-col gap-4" : "hidden"}>
              <CopywritingTab
                category={session.category}
                onGenerated={setCopyResult}
                result={copyResult}
                sellingPoints={sellingPoints}
                sessionId={sessionId}
              />
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}