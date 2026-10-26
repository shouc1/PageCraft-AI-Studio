"use client";

import { useEffect, useState } from "react";
import { Download, Loader2, Package, Plus } from "lucide-react";
import {
  downloadImages,
  generateDetailImages,
  getDetailPlan,
  getImageUrl,
  imageExt,
  type CopywritingResult,
  type DetailSlot,
  type SellingPoint,
} from "@/lib/api";
import { composePrompt } from "./shared";
import { GenerationCard, ProgressBar } from "./GenerationCard";
import { useBatchGeneration } from "./useBatchGeneration";
import { TextLayerCanvas } from "./TextLayerCanvas";

function detailTail(slot: DetailSlot): string {
  return slot.desc || slot.prompt_hint || slot.slot;
}

/**
 * 详情页生成：F-D1 结构规划 / F-D2 图文混排文字层 / F-D3 确认与生成。
 */
export function DetailTab({
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
  const [slots, setSlots] = useState<DetailSlot[]>([]);
  const [prompts, setPrompts] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [planError, setPlanError] = useState("");
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
            const slotName =
              slots[t.image_index ?? -1]?.slot || "详情图";
            return `详情图-${slotName}-${t.id.slice(0, 8)}.${imageExt(t.result_image!)}`;
          },
        }))
      );
      if (failed > 0) alert(`下载完成：${ok} 张成功，${failed} 张失败`);
    } finally {
      setBatchDownloading(false);
    }
  }

  // 类目变化时重新拉取详情结构规划
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setPlanError("");
    getDetailPlan(sessionId)
      .then((plan) => {
        if (cancelled) return;
        setSlots(plan.slots);
      })
      .catch((err) => {
        if (!cancelled)
          setPlanError(err instanceof Error ? err.message : "详情规划加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, category]);

  // 定位 / 类目 / 卖点 / 风格任一变化，重算每张 prompt
  useEffect(() => {
    setPrompts(
      slots.map((s) => composePrompt(category, sellingPoints, style, detailTail(s)))
    );
  }, [slots, category, sellingPoints, style]);

  function subtaskForIndex(index: number) {
    return subtasks.find((t) => t.image_index === index) || subtasks[index];
  }

  function updateDesc(index: number, value: string) {
    setSlots((prev) => prev.map((s, i) => (i === index ? { ...s, desc: value } : s)));
  }

  function removeSlot(index: number) {
    setSlots((prev) => prev.filter((_, i) => i !== index));
  }

  function addSlot() {
    setSlots((prev) => [
      ...prev,
      { index: prev.length, slot: "自定义", desc: "", prompt_hint: "" },
    ]);
  }

  const canGenerate =
    prompts.length > 0 && prompts.every((p) => p.trim()) && !generating;

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
      await runBatch(() => generateDetailImages(sessionId, { prompts: valid }));
    } catch (err) {
      alert(err instanceof Error ? err.message : "批量生成失败");
    }
  }

  // 文字层可回填的文案：卖点资产 + 文案模块产出（保证三处文案一致）
  const quickTexts = [
    ...sellingPoints.map((p) => ({ label: `卖点 · ${p.point}`, text: p.point })),
    ...(copywriting?.plans ?? []).flatMap((p) => [
      { label: `${p.type} · 标题`, text: p.title },
      { label: `${p.type} · 主图文案`, text: p.main_copy },
    ]),
  ].filter((q) => q.text.trim());

  return (
    <>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-ink">
            详情页结构规划（{slots.length} 张）
          </h2>
          <p className="text-xs text-slate-500">
            调整定位说明会自动更新 prompt
          </p>
        </div>
        <button
          className="flex items-center gap-1 text-xs text-blue-600 hover:underline"
          onClick={addSlot}
          type="button"
        >
          <Plus className="h-3.5 w-3.5" />
          添加定位
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
        </div>
      ) : planError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-600">{planError}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {slots.map((slot, i) => {
            const st = subtaskForIndex(i);
            return (
              <GenerationCard
                description={
                  <input
                    className="w-full rounded border border-line px-2 py-1 text-xs text-slate-600 outline-none focus:border-slate-400"
                    onChange={(e) => updateDesc(i, e.target.value)}
                    placeholder="定位说明（会影响 prompt）"
                    value={slot.desc}
                  />
                }
                disabled={generating}
                index={i}
                key={i}
                label={slot.slot}
                onEditText={() => {
                  const url = st?.result_image ? getImageUrl(st.result_image) : null;
                  if (url) setEditingImage(url);
                }}
                onPromptChange={(v) =>
                  setPrompts((prev) => prev.map((p, idx) => (idx === i ? v : p)))
                }
                onRegenerate={regenerate}
                onRemove={() => removeSlot(i)}
                prompt={prompts[i] || ""}
                subtask={st}
              />
            );
          })}
        </div>
      )}

      <div className="rounded-lg border border-line bg-panel p-4">
        <div className="flex items-center justify-between">
          <div className="text-sm text-slate-600">
            {generating
              ? `生成中：第 ${doneCount + 1}/${slots.length} 张`
              : subtasks.length > 0
                ? `已完成 ${doneCount}/${subtasks.length} 张`
                : "确认每张定位与 prompt 后批量生成"}
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
              {generating ? "生成中..." : `生成 ${slots.length} 张详情图`}
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