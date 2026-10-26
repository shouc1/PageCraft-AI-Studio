"use client";

import { useState, type ReactNode } from "react";
import { AlertTriangle, Download, Loader2, PenLine, RefreshCw, Trash2 } from "lucide-react";
import { downloadImage, getImageUrl, imageExt, type Task } from "@/lib/api";

const STATUS_META: Record<string, { label: string; cls: string }> = {
  pending: { label: "排队中", cls: "bg-slate-100 text-slate-600" },
  planning: { label: "prompt 扩写中", cls: "bg-violet-100 text-violet-700" },
  generating: { label: "生成中", cls: "bg-blue-100 text-blue-700" },
  saving: { label: "保存中", cls: "bg-blue-100 text-blue-700" },
  done: { label: "已完成", cls: "bg-emerald-100 text-emerald-700" },
  failed: { label: "失败", cls: "bg-red-100 text-red-700" },
};

const PROGRESS_TONE: Record<string, string> = {
  pending: "bg-slate-400",
  planning: "bg-violet-500",
  generating: "bg-blue-500",
  saving: "bg-blue-500",
  done: "bg-emerald-500",
  failed: "bg-red-500",
};

const IN_FLIGHT = new Set(["pending", "planning", "generating", "saving"]);

/** 通用进度条：value 0~100，进行中带呼吸动画。 */
export function ProgressBar({
  value,
  status,
}: {
  value: number;
  status?: string;
}) {
  const width = Math.min(100, Math.max(0, value));
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
      <div
        className={`h-full rounded-full transition-all duration-500 ${
          PROGRESS_TONE[status || ""] || "bg-slate-400"
        } ${status && IN_FLIGHT.has(status) ? "animate-pulse" : ""}`}
        style={{ width: `${width}%` }}
      />
    </div>
  );
}

/** 主图 / 详情页共用的一张生成卡：定位 + prompt 编辑 + 结果 + 重生成。 */
export function GenerationCard({
  index,
  label,
  description,
  prompt,
  subtask,
  disabled,
  onPromptChange,
  onRegenerate,
  onRemove,
  onEditText,
}: {
  index: number;
  label: string;
  description?: ReactNode;
  prompt: string;
  subtask?: Task;
  disabled?: boolean;
  onPromptChange: (value: string) => void;
  onRegenerate: (taskId: string) => void;
  onRemove?: () => void;
  onEditText?: () => void;
}) {
  const status = subtask?.status;
  const meta = status ? STATUS_META[status] : undefined;
  const consistency = subtask?.consistency;
  const distortion = consistency?.distortion_suspected === true;
  const consistencyWarning =
    typeof consistency?.warning === "string" ? consistency.warning : null;
  const [downloading, setDownloading] = useState(false);

  async function handleDownload() {
    const url = subtask?.result_image ? getImageUrl(subtask.result_image) : null;
    if (!url || downloading) return;
    setDownloading(true);
    try {
      const ext = imageExt(subtask!.result_image!);
      const safeLabel = label.replace(/[\\/:*?"<>|]/g, "_");
      await downloadImage(url, `${index + 1}-${safeLabel}-${subtask!.id.slice(0, 8)}.${ext}`);
    } catch (e) {
      alert(e instanceof Error ? e.message : "下载失败");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="flex flex-col rounded-lg border border-line bg-panel p-3">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <span className="text-sm font-medium text-ink">
            {index + 1}. {label}
          </span>
          {description && (
            <div className="mt-1 text-xs text-slate-500">{description}</div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {meta && (
            <span
              className={`rounded px-2 py-0.5 text-xs font-medium ${meta.cls}`}
            >
              {meta.label}
            </span>
          )}
          {onRemove && (
            <button
              className="rounded p-1 text-slate-400 transition hover:bg-red-50 hover:text-red-600"
              onClick={onRemove}
              title="移除该定位"
              type="button"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      <textarea
        className="min-h-20 w-full resize-none rounded-md border border-line bg-white p-2 text-xs leading-5 text-slate-700 outline-none focus:border-slate-400"
        onChange={(e) => onPromptChange(e.target.value)}
        value={prompt}
      />

      {subtask?.result_image && (
        <div className="group relative mt-2">
          <img
            alt={`${label} 结果`}
            className="aspect-square w-full rounded-md border border-line object-cover"
            src={getImageUrl(subtask.result_image) || ""}
          />
          <button
            className="absolute right-2 top-2 hidden items-center gap-1 rounded-md bg-black/60 px-2 py-1 text-xs font-medium text-white backdrop-blur transition hover:bg-black/80 group-hover:flex disabled:opacity-60"
            disabled={downloading}
            onClick={handleDownload}
            title="保存图片"
            type="button"
          >
            {downloading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )}
            下载
          </button>
          {distortion && (
            <div className="absolute left-2 top-2 flex items-center gap-1 rounded bg-amber-500 px-2 py-1 text-xs text-white">
              <AlertTriangle className="h-3.5 w-3.5" />
              疑似失真
            </div>
          )}
        </div>
      )}

      {consistencyWarning && subtask?.result_image && (
        <p className="mt-1 flex items-start gap-1 text-xs text-amber-600">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
          {consistencyWarning}
        </p>
      )}

      {subtask && !subtask.error_message && (
        <div className="mt-2">
          <ProgressBar value={subtask.progress} status={status} />
        </div>
      )}

      {subtask && (
        <div className="mt-2 flex items-center justify-between">
          {subtask.error_message ? (
            <span className="min-w-0 flex-1 truncate pr-2 text-xs text-red-600">
              {subtask.error_message}
            </span>
          ) : (
            <span className="text-xs text-slate-400">{subtask.progress}%</span>
          )}
          <button
            className="flex h-8 shrink-0 items-center gap-1 rounded-md border border-line bg-white px-2 text-xs text-slate-600 hover:bg-slate-50 disabled:text-slate-300"
            disabled={disabled}
            onClick={() => onRegenerate(subtask.id)}
            type="button"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            重生成
          </button>
        </div>
      )}

      {onEditText && subtask?.result_image && (
        <button
          className="mt-2 flex h-8 w-full items-center justify-center gap-1 rounded-md border border-blue-200 bg-blue-50 text-xs font-medium text-blue-700 hover:bg-blue-100"
          onClick={onEditText}
          type="button"
        >
          <PenLine className="h-3.5 w-3.5" />
          图文混排 · 编辑文字
        </button>
      )}
    </div>
  );
}