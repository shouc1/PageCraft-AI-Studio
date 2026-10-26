"use client";

import { useState } from "react";
import { Loader2, Save, X } from "lucide-react";
import { updateStyle, type StyleEntry } from "@/lib/api";

/** 可编辑字段配置（顺序即表单顺序；风格名是条目标识，不可编辑）。 */
const EDITABLE_FIELDS = [
  { key: "products", label: "适用商品", multiline: false },
  { key: "colors", label: "配色", multiline: false },
  { key: "elements", label: "元素", multiline: false },
  { key: "lighting", label: "光线", multiline: false },
  { key: "background", label: "背景", multiline: false },
  { key: "composition", label: "构图", multiline: false },
  { key: "prompt_template", label: "prompt 模板", multiline: true },
  { key: "negative_prompt", label: "负面提示", multiline: true },
] as const;

type FieldKey = (typeof EDITABLE_FIELDS)[number]["key"];

type FieldValues = Record<FieldKey, string>;

/** kb 字段为单行结构（后端拒绝换行），保存前把换行/连续空白压成单空格。 */
function normalize(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

/** 风格编辑弹窗：8 个字段级编辑，写回 kb 源文件并触发后台索引重建。 */
export function StyleEditModal({
  style,
  onClose,
  onSaved,
}: {
  style: StyleEntry;
  onClose: () => void;
  onSaved: (updated: StyleEntry) => void;
}) {
  const [values, setValues] = useState<FieldValues>(() => ({
    products: style.products,
    colors: style.colors,
    elements: style.elements,
    lighting: style.lighting,
    background: style.background,
    composition: style.composition,
    prompt_template: style.prompt_template,
    negative_prompt: style.negative_prompt,
  }));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSave() {
    if (saving) return;
    setError("");

    // 只提交发生变化的字段（后端要求至少 1 个更新字段）
    const patch: Partial<FieldValues> = {};
    for (const field of EDITABLE_FIELDS) {
      const value = normalize(values[field.key]);
      if (value !== style[field.key]) patch[field.key] = value;
    }
    if (Object.keys(patch).length === 0) {
      onClose();
      return;
    }

    // 前端预校验，与后端规则一致（prompt 模板清空 / 含 --- 分隔符）
    if ("prompt_template" in patch && !patch.prompt_template) {
      setError("prompt 模板不允许为空");
      return;
    }
    for (const [key, value] of Object.entries(patch)) {
      if (value && value.includes("---")) {
        setError(`「${EDITABLE_FIELDS.find((f) => f.key === key)?.label}」不允许包含 --- 分隔符`);
        return;
      }
    }

    setSaving(true);
    try {
      const updated = await updateStyle(style.name, patch);
      onSaved(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败，请确认后端已启动");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={saving ? undefined : onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-lg bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-ink">
              编辑风格：{style.name}
            </h2>
            <p className="mt-0.5 text-xs text-slate-400">
              来源 {style.source} · 保存后写回知识库并自动重建 RAG 索引
            </p>
          </div>
          <button
            className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            disabled={saving}
            onClick={onClose}
            type="button"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* 表单主体 */}
        <div className="min-h-0 flex-1 overflow-auto px-4 py-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {EDITABLE_FIELDS.map((field) => (
              <div
                className={field.multiline ? "md:col-span-2" : ""}
                key={field.key}
              >
                <label
                  className="mb-1 block text-xs font-medium text-slate-600"
                  htmlFor={`style-${field.key}`}
                >
                  {field.label}
                </label>
                {field.multiline ? (
                  <textarea
                    className="min-h-16 w-full resize-y rounded-md border border-line bg-white p-2 text-xs leading-5 text-slate-700 outline-none focus:border-slate-400"
                    id={`style-${field.key}`}
                    onChange={(e) =>
                      setValues((prev) => ({
                        ...prev,
                        [field.key]: e.target.value,
                      }))
                    }
                    value={values[field.key]}
                  />
                ) : (
                  <input
                    className="h-9 w-full rounded-md border border-line bg-white px-2 text-xs text-slate-700 outline-none focus:border-slate-400"
                    id={`style-${field.key}`}
                    onChange={(e) =>
                      setValues((prev) => ({
                        ...prev,
                        [field.key]: e.target.value,
                      }))
                    }
                    value={values[field.key]}
                  />
                )}
                {field.key === "prompt_template" && (
                  <p className="mt-1 text-xs text-slate-400">
                    {"{product} 会被替换为商品描述；保存时换行自动转为空格"}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* 底部操作 */}
        <div className="border-t border-line px-4 py-3">
          {error && (
            <p className="mb-2 break-all text-xs text-red-600">{error}</p>
          )}
          <div className="flex items-center justify-end gap-2">
            <button
              className="h-9 rounded-md border border-line bg-white px-4 text-xs text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-300"
              disabled={saving}
              onClick={onClose}
              type="button"
            >
              取消
            </button>
            <button
              className="flex h-9 items-center gap-1.5 rounded-md bg-ink px-4 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
              disabled={saving}
              onClick={handleSave}
              type="button"
            >
              {saving ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5" />
              )}
              {saving ? "保存中..." : "保存"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
