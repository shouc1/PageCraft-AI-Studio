"use client";

import { useEffect, useRef, useState } from "react";
import {
  Bold,
  Download,
  Plus,
  Trash2,
  Type,
  X,
} from "lucide-react";

type FontKey = "sans" | "serif" | "mono";

type TextElement = {
  id: string;
  text: string;
  /** 左锚点横坐标占比 0~1 */
  xf: number;
  /** 顶部纵坐标占比 0~1 */
  yf: number;
  /** 编辑画布像素字号（导出按比例换算） */
  fontSize: number;
  color: string;
  bold: boolean;
  fontKey: FontKey;
};

export type QuickText = { label: string; text: string };

const FONTS: Record<FontKey, string> = {
  sans: "'PingFang SC','Microsoft YaHei','Noto Sans SC',sans-serif",
  serif: "Georgia,'Songti SC','SimSun',serif",
  mono: "ui-monospace,'SF Mono',Consolas,monospace",
};

const PRESET_COLORS = ["#1f2937", "#ffffff", "#dc2626", "#f59e0b", "#2563eb", "#f43f5e"];

const MAX_W = 440;
const MAX_H = 560;

function genId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);
}

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

function computeDisplay(natural: { w: number; h: number } | null) {
  const w = natural?.w ?? 750;
  const h = natural?.h ?? 1200;
  const scale = Math.min(1, MAX_W / w, MAX_H / h);
  return {
    displayW: Math.round(w * scale),
    displayH: Math.round(h * scale),
  };
}

/** F-D2 图文混排文字层：底图 + 可拖拽文字 + Canvas 合成导出 PNG。 */
export function TextLayerCanvas({
  imageSrc,
  quickTexts,
  onClose,
}: {
  imageSrc: string;
  quickTexts: QuickText[];
  onClose: () => void;
}) {
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [elements, setElements] = useState<TextElement[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const stageRef = useRef<HTMLDivElement | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const dragRef = useRef<{
    id: string;
    startX: number;
    startY: number;
    startXf: number;
    startYf: number;
  } | null>(null);

  // 以 crossOrigin 加载底图，供导出合成使用
  useEffect(() => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      imgRef.current = img;
      setNatural({ w: img.naturalWidth, h: img.naturalHeight });
    };
    img.src = imageSrc;
  }, [imageSrc]);

  const { displayW, displayH } = computeDisplay(natural);
  const selected = elements.find((el) => el.id === selectedId) || null;

  function startDrag(e: React.PointerEvent, el: TextElement) {
    e.stopPropagation();
    setSelectedId(el.id);
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect) return;
    dragRef.current = {
      id: el.id,
      startX: e.clientX,
      startY: e.clientY,
      startXf: el.xf,
      startYf: el.yf,
    };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    void rect;
  }

  function onDragMove(e: React.PointerEvent) {
    const d = dragRef.current;
    const rect = stageRef.current?.getBoundingClientRect();
    if (!d || !rect || rect.width === 0 || rect.height === 0) return;
    const dx = (e.clientX - d.startX) / rect.width;
    const dy = (e.clientY - d.startY) / rect.height;
    setElements((prev) =>
      prev.map((el) =>
        el.id === d.id
          ? {
              ...el,
              xf: clamp(d.startXf + dx, 0, 1),
              yf: clamp(d.startYf + dy, 0, 1),
            }
          : el
      )
    );
  }

  function endDrag(e: React.PointerEvent) {
    dragRef.current = null;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  }

  function updateSelected(patch: Partial<TextElement>) {
    if (!selectedId) return;
    setElements((prev) =>
      prev.map((el) => (el.id === selectedId ? { ...el, ...patch } : el))
    );
  }

  function addText(text = "输入文字") {
    const el: TextElement = {
      id: genId(),
      text,
      xf: 0.08,
      yf: clamp(0.04 + elements.length * 0.12, 0.04, 0.85),
      fontSize: 28,
      color: "#1f2937",
      bold: false,
      fontKey: "sans",
    };
    setElements((prev) => [...prev, el]);
    setSelectedId(el.id);
  }

  function removeSelected() {
    if (!selectedId) return;
    setElements((prev) => prev.filter((el) => el.id !== selectedId));
    setSelectedId(null);
  }

  function exportPng() {
    const img = imgRef.current;
    if (!img || !natural) {
      alert("底图尚未就绪，无法导出");
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = natural.w;
    canvas.height = natural.h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(img, 0, 0, natural.w, natural.h);

    const scale = natural.w / displayW;
    ctx.textBaseline = "top";
    for (const el of elements) {
      if (!el.text.trim()) continue;
      const fs = Math.max(4, el.fontSize * scale);
      ctx.font = `${el.bold ? "bold " : ""}${fs}px ${FONTS[el.fontKey]}`;
      ctx.fillStyle = el.color;
      const lines = el.text.split("\n");
      lines.forEach((line, i) => {
        ctx.fillText(
          line,
          el.xf * natural.w,
          el.yf * natural.h + i * fs * 1.4
        );
      });
    }

    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/png");
    a.download = `detail-copy-${Date.now()}.png`;
    a.click();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="flex h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-lg bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="flex items-center gap-2">
            <Type className="h-4 w-4 text-slate-500" />
            <h2 className="text-sm font-semibold text-ink">图文混排 · 文字层</h2>
          </div>
          <button
            className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            onClick={onClose}
            type="button"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* 主体 */}
        <div className="flex min-h-0 flex-1">
          {/* 画布 */}
          <div className="flex flex-1 items-center justify-center overflow-auto bg-slate-100 p-6">
            <div
              className="relative overflow-hidden rounded-lg border border-slate-300 bg-white shadow"
              onPointerDown={() => setSelectedId(null)}
              ref={stageRef}
              style={{ width: displayW, height: displayH }}
            >
              <img
                alt="详情底图"
                className="pointer-events-none h-full w-full object-cover"
                src={imageSrc}
              />
              {elements.map((el) => (
                <div
                  className="absolute cursor-move select-none whitespace-pre-wrap break-words"
                  key={el.id}
                  onPointerCancel={endDrag}
                  onPointerDown={(e) => startDrag(e, el)}
                  onPointerMove={onDragMove}
                  onPointerUp={endDrag}
                  style={{
                    left: `${el.xf * 100}%`,
                    top: `${el.yf * 100}%`,
                    fontSize: el.fontSize,
                    color: el.color,
                    fontWeight: el.bold ? 700 : 400,
                    fontFamily: FONTS[el.fontKey],
                    lineHeight: 1.4,
                  }}
                >
                  {el.text || "输入文字"}
                </div>
              ))}
            </div>
          </div>

          {/* 属性 / 快速填充 */}
          <aside className="flex w-72 flex-col gap-4 overflow-y-auto border-l border-line bg-slate-50 p-4">
            <div>
              <h3 className="mb-2 text-xs font-semibold text-slate-500">
                文字属性{selected ? "" : "（选中文字后可编辑）"}
              </h3>
              {selected ? (
                <div className="space-y-3">
                  <textarea
                    className="min-h-24 w-full resize-none rounded-md border border-line bg-white p-2 text-sm outline-none focus:border-slate-400"
                    onChange={(e) => updateSelected({ text: e.target.value })}
                    placeholder="输入文字，支持换行"
                    value={selected.text}
                  />

                  <label className="block text-xs text-slate-500">
                    字号
                    <input
                      className="mt-1 w-full"
                      max={120}
                      min={10}
                      onChange={(e) =>
                        updateSelected({ fontSize: Number(e.target.value) })
                      }
                      type="range"
                      value={selected.fontSize}
                    />
                  </label>

                  <div className="flex items-center gap-2">
                    <label className="block flex-1 text-xs text-slate-500">
                      字体
                      <select
                        className="mt-1 w-full rounded-md border border-line bg-white px-2 py-1.5 text-sm outline-none focus:border-slate-400"
                        onChange={(e) =>
                          updateSelected({ fontKey: e.target.value as FontKey })
                        }
                        value={selected.fontKey}
                      >
                        <option value="sans">黑体 / 无衬线</option>
                        <option value="serif">宋体 / 衬线</option>
                        <option value="mono">等宽</option>
                      </select>
                    </label>
                    <button
                      className={`mt-4 flex h-9 w-9 items-center justify-center rounded-md border ${
                        selected.bold
                          ? "border-ink bg-ink text-white"
                          : "border-line bg-white text-slate-600"
                      }`}
                      onClick={() => updateSelected({ bold: !selected.bold })}
                      title="加粗"
                      type="button"
                    >
                      <Bold className="h-4 w-4" />
                    </button>
                  </div>

                  <div>
                    <span className="text-xs text-slate-500">颜色</span>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      {PRESET_COLORS.map((c) => (
                        <button
                          className={`h-6 w-6 rounded-full border ${
                            selected.color === c
                              ? "ring-2 ring-ink"
                              : "border-slate-300"
                          }`}
                          key={c}
                          onClick={() => updateSelected({ color: c })}
                          style={{ backgroundColor: c }}
                          type="button"
                        />
                      ))}
                      <input
                        className="h-6 w-8 cursor-pointer rounded border border-line"
                        onChange={(e) => updateSelected({ color: e.target.value })}
                        title="自定义颜色"
                        type="color"
                        value={selected.color}
                      />
                    </div>
                  </div>

                  <button
                    className="flex h-9 w-full items-center justify-center gap-1 rounded-md border border-red-200 bg-white text-sm text-red-600 hover:bg-red-50"
                    onClick={removeSelected}
                    type="button"
                  >
                    <Trash2 className="h-4 w-4" />
                    删除文字
                  </button>
                </div>
              ) : (
                <p className="text-xs text-slate-400">
                  点击画布中的文字以编辑；在画布空白处点按可取消选中。
                </p>
              )}
            </div>

            <div>
              <h3 className="mb-2 text-xs font-semibold text-slate-500">
                从卖点 / 文案回填
              </h3>
              <div className="flex flex-col gap-1.5">
                {quickTexts.length === 0 ? (
                  <p className="text-xs text-slate-400">
                    暂无卖点或文案资产，可先提取卖点或生成文案。
                  </p>
                ) : (
                  quickTexts.map((q, i) => (
                    <button
                      className="truncate rounded-md border border-line bg-white px-2 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50"
                      key={i}
                      onClick={() => addText(q.text)}
                      title={q.label}
                      type="button"
                    >
                      {q.label}
                    </button>
                  ))
                )}
              </div>
            </div>
          </aside>
        </div>

        {/* 底部 */}
        <div className="flex items-center justify-between border-t border-line px-4 py-3">
          <div className="text-xs text-slate-500">
            拖动文字定位；导出按 750px 底图原尺寸合成
          </div>
          <div className="flex items-center gap-2">
            <button
              className="flex h-9 items-center gap-2 rounded-md border border-line px-3 text-sm text-slate-700 hover:bg-slate-50"
              onClick={() => addText()}
              type="button"
            >
              <Plus className="h-4 w-4" />
              添加文字
            </button>
            <button
              className="flex h-9 items-center gap-2 rounded-md bg-ink px-3 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
              disabled={!natural}
              onClick={exportPng}
              type="button"
            >
              <Download className="h-4 w-4" />
              导出 PNG
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}