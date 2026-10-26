"use client";

import { useEffect, useMemo, useState } from "react";
import { Library, Loader2, RefreshCw, Search } from "lucide-react";
import { AppHeader } from "@/components/layout/AppHeader";
import { StyleEditModal } from "@/components/styles/StyleEditModal";
import { listStyles, type StyleEntry } from "@/lib/api";

/** 风格库管理页（需求 v2 F-M3）：查看 / 搜索 / 编辑 kb 风格模板。 */
export default function StylesPage() {
  const [styles, setStyles] = useState<StyleEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [editing, setEditing] = useState<StyleEntry | null>(null);
  const [savedTip, setSavedTip] = useState("");

  async function load() {
    setLoading(true);
    setLoadError(false);
    try {
      const res = await listStyles();
      setStyles(res.styles);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  // 保存成功横幅 3 秒自动消失
  useEffect(() => {
    if (!savedTip) return;
    const timer = setTimeout(() => setSavedTip(""), 3000);
    return () => clearTimeout(timer);
  }, [savedTip]);

  // 本地过滤：风格名 / 适用商品 / 配色（23 条量级，无需走后端）
  const filtered = useMemo(() => {
    const kw = keyword.trim();
    if (!kw) return styles;
    return styles.filter(
      (s) =>
        s.name.includes(kw) ||
        s.products.includes(kw) ||
        s.colors.includes(kw)
    );
  }, [styles, keyword]);

  function handleSaved(updated: StyleEntry) {
    setStyles((prev) =>
      prev.map((s) => (s.name === updated.name ? updated : s))
    );
    setSavedTip(`风格「${updated.name}」已保存，RAG 索引后台重建中`);
    setEditing(null);
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <AppHeader />

      <div className="mx-auto max-w-5xl p-6">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">风格知识库</h1>
            <p className="mt-1 text-sm text-slate-500">
              生成主图 / 详情页时 RAG 检索的风格模板，共 {styles.length} 个风格
            </p>
          </div>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              className="h-10 w-64 rounded-lg border border-line bg-white pl-8 pr-3 text-sm text-slate-700 outline-none focus:border-slate-400"
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="搜索风格名 / 适用商品 / 配色"
              value={keyword}
            />
          </div>
        </div>

        {savedTip && (
          <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-700">
            {savedTip}
          </div>
        )}

        {loading ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            加载中...
          </div>
        ) : loadError ? (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white py-16 text-center">
            <p className="text-sm font-medium text-slate-700">风格库加载失败</p>
            <p className="mt-1 text-xs text-slate-500">
              请确认后端已启动（127.0.0.1:8000）
            </p>
            <button
              className="mt-4 flex h-9 items-center gap-1.5 rounded-md border border-line bg-white px-3 text-xs text-slate-600 hover:bg-slate-50"
              onClick={load}
              type="button"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              重试
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white py-16 text-center">
            <Library className="mb-3 h-10 w-10 text-slate-300" />
            <p className="text-sm font-medium text-slate-700">
              {keyword ? "没有匹配的风格" : "风格库为空"}
            </p>
            {keyword && (
              <p className="mt-1 text-xs text-slate-500">
                换个关键词试试，如「极简」「美妆」「莫兰迪」
              </p>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {filtered.map((style) => (
              <button
                className="flex flex-col rounded-lg border border-line bg-panel p-4 text-left transition hover:shadow-md"
                key={style.name}
                onClick={() => setEditing(style)}
                type="button"
              >
                <div className="flex items-center justify-between gap-2">
                  <h2 className="truncate text-base font-semibold text-slate-900">
                    {style.name}
                  </h2>
                  <span className="shrink-0 rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                    {style.source}
                  </span>
                </div>
                <p className="mt-2 line-clamp-1 text-xs text-slate-500">
                  <span className="text-slate-400">适用：</span>
                  {style.products || "—"}
                </p>
                <p className="mt-1 line-clamp-1 text-xs text-slate-500">
                  <span className="text-slate-400">配色：</span>
                  {style.colors || "—"}
                </p>
                <p className="mt-2 line-clamp-2 border-t border-line pt-2 font-mono text-xs leading-5 text-slate-500">
                  {style.prompt_template || "—"}
                </p>
              </button>
            ))}
          </div>
        )}
      </div>

      {editing && (
        <StyleEditModal
          key={editing.name}
          onClose={() => setEditing(null)}
          onSaved={handleSaved}
          style={editing}
        />
      )}
    </main>
  );
}
