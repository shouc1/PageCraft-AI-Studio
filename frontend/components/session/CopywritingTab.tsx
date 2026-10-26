"use client";

import { useState } from "react";
import { AlertTriangle, Flame, Loader2, Sparkles } from "lucide-react";
import {
  generateCopywriting,
  type CopyIssue,
  type CopywritingResult,
  type SellingPoint,
} from "@/lib/api";

const FIELD_LABEL: Record<string, string> = {
  title: "标题",
  main_copy: "主图文案",
  detail_copy: "详情页文案",
};

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function renderHighlighted(text: string, issues: CopyIssue[], field: string) {
  const words = issues.filter((i) => i.field === field && i.word).map((i) => i.word);
  if (words.length === 0) return text;
  const lower = new Set(words.map((w) => w.toLowerCase()));
  const regex = new RegExp(`(${words.map(escapeRegExp).join("|")})`, "gi");
  return text.split(regex).map((part, i) =>
    lower.has(part.toLowerCase()) ? (
      <mark className="rounded bg-red-100 px-0.5 text-red-600" key={i}>
        {part}
      </mark>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}

/** 营销文案生成（F-C1 三方案 / F-C2 合规过滤 / F-C3 热点注入）。 */
export function CopywritingTab({
  sessionId,
  category,
  sellingPoints,
  result,
  onGenerated,
}: {
  sessionId: string;
  category: string;
  sellingPoints: SellingPoint[];
  result: CopywritingResult | null;
  onGenerated: (result: CopywritingResult) => void;
}) {
  const [hint, setHint] = useState("");
  const [generating, setGenerating] = useState(false);

  async function handleGenerate() {
    setGenerating(true);
    try {
      onGenerated(await generateCopywriting(sessionId, hint));
    } catch (err) {
      alert(err instanceof Error ? err.message : "文案生成失败");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-panel p-3">
        <input
          className="min-w-0 flex-1 rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-slate-400"
          onChange={(e) => setHint(e.target.value)}
          placeholder="补充营销需求（可选）：场景 / 语气 / 目标人群"
          value={hint}
        />
        <button
          className="flex h-10 items-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:bg-slate-400"
          disabled={generating}
          onClick={handleGenerate}
          type="button"
        >
          {generating ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="h-4 w-4" />
          )}
          {generating ? "生成中..." : "生成文案"}
        </button>
      </div>
      <p className="text-xs text-slate-400">
        {category ? `类目：${category}` : "未识别类目"} · 基于已保存的
        {sellingPoints.length} 条卖点资产生成
      </p>

      {result && (
        <>
          {result.hotspots.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
              <Flame className="h-4 w-4 text-amber-500" />
              <span className="text-xs font-medium text-amber-700">
                热点注入：
              </span>
              {result.hotspots.map((h) => (
                <span
                  className="rounded bg-white px-2 py-1 text-xs text-slate-700"
                  key={h.name}
                >
                  {h.name}（{h.hint}）
                </span>
              ))}
            </div>
          )}

          <div className="grid grid-cols-1 gap-3">
            {result.plans.map((plan, i) => (
              <div
                className="rounded-lg border border-line bg-panel p-4"
                key={i}
              >
                <div className="mb-3 flex items-center gap-2">
                  <span className="rounded bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                    方案 {i + 1} · {plan.type}
                  </span>
                  <h3 className="text-sm font-semibold text-ink">
                    {renderHighlighted(plan.title, plan.issues, "title")}
                  </h3>
                </div>

                <div className="space-y-3 text-sm leading-6 text-slate-700">
                  <div>
                    <div className="text-xs text-slate-400">主图文案</div>
                    <p>{renderHighlighted(plan.main_copy, plan.issues, "main_copy")}</p>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400">详情页文案</div>
                    <p>{renderHighlighted(plan.detail_copy, plan.issues, "detail_copy")}</p>
                  </div>
                </div>

                {plan.issues.length > 0 && (
                  <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-3">
                    <div className="mb-1 flex items-center gap-1 text-xs font-medium text-red-700">
                      <AlertTriangle className="h-3.5 w-3.5" />
                      合规风险（{plan.issues.length}）
                    </div>
                    <ul className="space-y-1 text-xs text-red-600">
                      {plan.issues.map((issue, j) => (
                        <li key={j}>
                          {FIELD_LABEL[issue.field] || issue.field}「{issue.word}」→
                          建议改为「{issue.suggestion}」
                          {issue.count > 0 ? `（${issue.count} 处）` : ""}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}