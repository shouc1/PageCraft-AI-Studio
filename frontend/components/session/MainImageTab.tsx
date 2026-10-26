"use client";

import { useEffect, useState } from "react";
import { Download, Loader2, Package, RefreshCw } from "lucide-react";
import {
  downloadImages,
  generateMainImages,
  getImageUrl,
  imageExt,
  type CopywritingResult,
  type SellingPoint,
} from "@/lib/api";
import { composePrompt } from "./shared";
import { GenerationCard, ProgressBar } from "./GenerationCard";
import { useBatchGeneration } from "./useBatchGeneration";
import { TextLayerCanvas } from "./TextLayerCanvas";

/** 4 张主图的定位（需求 v2 F-M4：白底 / 场景 / 卖点特写 / 促销）。 */
const MAIN_ANGLES = [
  { label: "白底图", hint: "纯白背景，商品居中完整呈现，电商主图标准白底" },
  { label: "场景图", hint: "商品融入真实使用场景，氛围自然，突出体验感" },
  { label: "卖点特写", hint: "核心卖点局部特写，突出质感与工艺细节" },
  { label: "促销图", hint: "促销氛围，用色彩渐变与装饰色块传达优惠感，画面不出现任何文字、标语与价格数字" },
];

export function MainImageTab({
  sessionId,
  category,
  sellingPoints,
  style,
  copywriting,
  hasImages,
}: {
  sessionId: string;
  category: string;
  sellingPoints: SellingPoint[];
  style: string;
  copywriting?: CopywritingResult | null;
  hasImages: boolean;
}) {
  const [prompts, setPrompts] = useState<string[]>(() =>
    MAIN_ANGLES.map((a) => composePrompt(category, sellingPoints, style, a.hint))
  );
  const [editingImage, setEditingImage] = useState<string | null>(null);
  const [batchDownloading, setBatchDownloading] = useState(false);
  const { generating, subtasks, doneCount, runBatch, regenerate } =
    useBatchGeneration();

  const doneImages = subtasks.filter((t) => t.result_image);

  async function handleDownloadAll() {
    if (batchDownloading || !doneImages.length) return;
    setBatchDownloading(true);
    try {
      const { ok, failed } = await downloadImages(
        doneImages.map((t) => ({
          path: t.result_image!,
          filenameOf: () => {
            const angle =
              MAIN_ANGLES[t.image_index ?? -1] || MAIN_ANGLES[0];
            return `主图-${angle.label}-${t.id.slice(0, 8)}.${imageExt(t.result_image!)}`;
          },
        }))
      );
      if (failed > 0) alert(`下载完成：${ok} 张成功，${failed} 张失败`);
    } finally {
      setBatchDownloading(false);
    }
  }

  // 文字层可回填的文案：卖点资产 + 文案模块产出（与详情页同源，保证文案一致）
  const quickTexts = [
    ...sellingPoints.map((p) => ({ label: `卖点 · ${p.point}`, text: p.point })),
    ...(copywriting?.plans ?? []).flatMap((p) => [
      { label: `${p.type} · 标题`, text: p.title },
      { label: `${p.type} · 主图文案`, text: p.main_copy },
    ]),
  ].filter((q) => q.text.trim());

  // 类目/卖点/风格任一变化，同步刷新推荐 prompt（共享资产联动）。
  useEffect(() => {
    setPrompts(
      MAIN_ANGLES.map((a) => composePrompt(category, sellingPoints, style, a.hint))
    );
  }, [category, sellingPoints, style]);

  function subtaskForIndex(index: number) {
    return subtasks.find((t) => t.image_index === index) || subtasks[index];
  }

  const canGenerate =
    prompts.length === 4 && prompts.every((p) => p.trim()) && !generating;

  async function handleGenerate() {
    const valid = prompts.map((p) => p.trim());
    if (valid.some((p) => !p) || generating) return;
    // 空会话无参考图，将退化为纯文字生图（商品外观不可控），先确认
    if (
      !hasImages &&
      !confirm("当前没有上传商品图片，将按提示词纯文字生成，商品外观可能与实际不符。是否继续生成？")
    )
      return;
    try {
      await runBatch(() => generateMainImages(sessionId, { prompts: valid }));
    } catch (err) {
      alert(err instanceof Error ? err.message : "批量生成失败");
    }
  }

  return (
    <>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-ink">主图生成（4 张）</h2>
          <p className="text-xs text-slate-500">每张独立 prompt，可单独重生成</p>
        </div>
        <button
          className="flex items-center gap-1 text-xs text-blue-600 hover:underline"
          onClick={() =>
            setPrompts(
              MAIN_ANGLES.map((a) =>
                composePrompt(category, sellingPoints, style, a.hint)
              )
            )
          }
          type="button"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          重置推荐 prompt
        </button>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {MAIN_ANGLES.map((angle, i) => {
          const st = subtaskForIndex(i);
          return (
            <GenerationCard
              description={angle.hint}
              disabled={generating}
              index={i}
              key={angle.label}
              label={angle.label}
              onEditText={() => {
                const url = st?.result_image ? getImageUrl(st.result_image) : null;
                if (url) setEditingImage(url);
              }}
              onPromptChange={(v) =>
                setPrompts((prev) => prev.map((p, idx) => (idx === i ? v : p)))
              }
              onRegenerate={regenerate}
              prompt={prompts[i] || ""}
              subtask={st}
            />
          );
        })}
      </div>

      <div className="rounded-lg border border-line bg-panel p-4">
        <div className="flex items-center justify-between">
          <div className="text-sm text-slate-600">
            {generating
              ? `生成中：第 ${doneCount + 1}/4 张`
              : subtasks.length > 0
                ? `已完成 ${doneCount}/${subtasks.length} 张`
                : "确认 prompt 后开始批量生成"}
          </div>
          <div className="flex items-center gap-2">
            {doneImages.length > 0 && (
              <button
                className="flex h-10 items-center gap-2 rounded-lg border border-line bg-white px-4 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={batchDownloading || generating}
                onClick={handleDownloadAll}
                type="button"
              >
                {batchDownloading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
                {batchDownloading
                  ? "下载中..."
                  : `下载全部（${doneImages.length} 张）`}
              </button>
            )}
            <button
              className="flex h-10 items-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
              disabled={!canGenerate}
              onClick={handleGenerate}
              type="button"
            >
              {generating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Package className="h-4 w-4" />
              )}
              {generating ? "生成中..." : "生成 4 张主图"}
            </button>
          </div>
        </div>
        {subtasks.length > 0 && (
          <div className="mt-3">
            <ProgressBar
              value={(doneCount / subtasks.length) * 100}
              status={generating ? "generating" : "done"}
            />
          </div>
        )}
      </div>

      {editingImage && (
        <TextLayerCanvas
          imageSrc={editingImage}
          quickTexts={quickTexts}
          onClose={() => setEditingImage(null)}
        />
      )}
    </>
  );
}