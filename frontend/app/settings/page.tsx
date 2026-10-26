"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  RotateCcw,
} from "lucide-react";
import {
  getSettings,
  updateSettings,
  SECRET_SETTING_KEYS,
  LLM_PROVIDER_OPTIONS,
  IMAGE_PROVIDER_OPTIONS,
  type SettingItem,
  type SettingsOverview,
} from "@/lib/api";

type HealthInfo = {
  status: string;
  has_credentials: boolean;
  has_ark_credentials: boolean;
  has_dashscope_credentials: boolean;
  has_qwen_llm_credentials: boolean;
  llm_provider: string;
  image_provider: string;
  rag_enabled: boolean;
};

/** 设置项 key → 中文标签 */
const FIELD_LABELS: Record<string, string> = {
  ARK_API_KEY: "豆包 ARK API Key",
  DOUBAO_MODEL: "豆包模型接入点",
  VOLCENGINE_AK: "火山引擎 Access Key",
  VOLCENGINE_SK: "火山引擎 Secret Key",
  JIMENG_T2I_MODEL: "即梦模型 · 文生图（req_key）",
  JIMENG_I2I_MODEL: "即梦模型 · 图生图（req_key）",
  DASHSCOPE_API_KEY: "百炼 DashScope API Key",
  QWEN_IMAGE_MODEL: "千问生图模型",
  QWEN_TEXT_MODEL: "千问文本模型",
};

/** 各厂商展示的设置键（语言模型） */
const LLM_FIELDS: Record<string, string[]> = {
  doubao: ["ARK_API_KEY", "DOUBAO_MODEL"],
  qwen: ["DASHSCOPE_API_KEY", "QWEN_TEXT_MODEL"],
};

/** 各厂商展示的设置键（视觉模型） */
const IMAGE_FIELDS: Record<string, string[]> = {
  jimeng: ["VOLCENGINE_AK", "VOLCENGINE_SK", "JIMENG_T2I_MODEL", "JIMENG_I2I_MODEL"],
  qwen: ["DASHSCOPE_API_KEY", "QWEN_IMAGE_MODEL"],
};

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 凭证配置表单状态
  const [overview, setOverview] = useState<SettingsOverview | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ ok: boolean; text: string } | null>(
    null
  );

  const loadHealth = useCallback(() => {
    return fetch(
      `${process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000"}/api/health`
    )
      .then((r) => r.json())
      .then(setHealth)
      .catch((e) => setError(e.message));
  }, []);

  const loadSettings = useCallback(() => {
    return getSettings()
      .then((data) => {
        setOverview(data);
        setDrafts({}); // 重置草稿，避免旧输入残留
      })
      .catch((e) =>
        setBanner({ ok: false, text: `设置加载失败：${e.message}` })
      );
  }, []);

  useEffect(() => {
    Promise.all([loadHealth(), loadSettings()]).finally(() =>
      setLoading(false)
    );
  }, [loadHealth, loadSettings]);

  const submitUpdates = async (values: Record<string, string>, okText: string) => {
    setSaving(true);
    setBanner(null);
    try {
      const data = await updateSettings(values);
      setOverview(data);
      setDrafts({});
      setBanner({ ok: true, text: okText });
      loadHealth(); // 刷新凭证就绪状态
    } catch (e) {
      setBanner({ ok: false, text: `保存失败：${(e as Error).message}` });
    } finally {
      setSaving(false);
    }
  };

  // 保存：只提交有输入的键（留空 = 不改）
  const handleSave = () => {
    const values: Record<string, string> = {};
    for (const [key, val] of Object.entries(drafts)) {
      if (val.trim()) values[key] = val.trim();
    }
    if (!Object.keys(values).length) return;
    submitUpdates(values, "凭证已保存，立即生效");
  };

  // 一键回落 .env：发空字符串清除覆盖
  const handleReset = async (key: string) => {
    setResetting(key);
    await submitUpdates({ [key]: "" }, `${FIELD_LABELS[key] || key} 已回落 .env 默认值`);
    setResetting(null);
  };

  const hasDraft = Object.values(drafts).some((v) => v.trim());

  // 当前生效厂商（草稿优先，切换下拉即时联动字段区；保存后落库）
  const llmProvider =
    drafts.LLM_PROVIDER?.trim() || overview?.llm_provider || "doubao";
  const imageProvider =
    drafts.IMAGE_PROVIDER?.trim() || overview?.image_provider || "jimeng";

  const itemMap = new Map<string, SettingItem>(
    overview?.settings.map((s) => [s.key, s]) ?? []
  );

  const renderFields = (keys: string[], sectionPrefix: string) =>
    keys.map((key) => {
      const item = itemMap.get(key);
      if (!item) return null;
      return (
        <SettingField
          key={`${sectionPrefix}-${key}`}
          item={item}
          draft={drafts[item.key] ?? ""}
          resetting={resetting === item.key}
          onDraftChange={(v) =>
            setDrafts((prev) => ({ ...prev, [item.key]: v }))
          }
          onReset={() => handleReset(item.key)}
        />
      );
    });

  return (
    <main className="min-h-screen bg-slate-50 p-8">
      <div className="mx-auto max-w-3xl">
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← 返回会话列表
        </Link>
        <h1 className="mt-2 text-xl font-semibold text-slate-900">设置</h1>
        <p className="mt-1 text-sm text-slate-500">
          模型分语言模型与视觉模型两类，各自可切换厂商；页面只展示所选厂商的配置项。修改保存后立即生效，无需重启后端。
        </p>

        {loading ? (
          <div className="mt-6 flex items-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            正在连接后端...
          </div>
        ) : error ? (
          <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4">
            <div className="flex items-center gap-2 text-red-700">
              <XCircle className="h-5 w-5" />
              <span className="font-medium">后端连接失败</span>
            </div>
            <p className="mt-2 text-xs text-red-600 break-all">{error}</p>
            <p className="mt-2 text-xs text-slate-500">
              请确认后端已启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
            </p>
          </div>
        ) : health ? (
          <div className="mt-6 space-y-4">
            {banner && (
              <div
                className={`rounded-md p-3 text-xs ${
                  banner.ok
                    ? "bg-emerald-50 text-emerald-700"
                    : "bg-red-50 text-red-700"
                }`}
              >
                {banner.text}
              </div>
            )}

            {overview ? (
              <>
                <Section title="语言模型（类目识别 / 卖点提取 / 提示词扩写 / 文案）">
                  <ProviderSelect
                    label="语言模型厂商"
                    options={LLM_PROVIDER_OPTIONS}
                    value={llmProvider}
                    disabled={saving}
                    onChange={(v) =>
                      setDrafts((prev) => ({ ...prev, LLM_PROVIDER: v }))
                    }
                  />
                  {renderFields(LLM_FIELDS[llmProvider] ?? [], "llm")}
                </Section>

                <Section title="视觉模型（主图 / 详情页图片生成）">
                  <ProviderSelect
                    label="视觉模型厂商"
                    options={IMAGE_PROVIDER_OPTIONS}
                    value={imageProvider}
                    disabled={saving}
                    onChange={(v) =>
                      setDrafts((prev) => ({ ...prev, IMAGE_PROVIDER: v }))
                    }
                  />
                  {renderFields(IMAGE_FIELDS[imageProvider] ?? [], "img")}
                </Section>

                <div className="flex items-center gap-3">
                  <button
                    onClick={handleSave}
                    disabled={!hasDraft || saving}
                    className="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {saving ? (
                      <span className="flex items-center gap-1.5">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        保存中...
                      </span>
                    ) : (
                      "保存修改"
                    )}
                  </button>
                  {hasDraft && !saving && (
                    <button
                      onClick={() => setDrafts({})}
                      className="text-xs text-slate-500 hover:text-slate-700"
                    >
                      放弃修改
                    </button>
                  )}
                  {!hasDraft && (
                    <span className="text-xs text-slate-400">
                      切换厂商下拉即可联动显示对应配置项
                    </span>
                  )}
                </div>

                <p className="text-xs text-slate-400">
                  密钥留空表示不修改；输入框显示的是脱敏后的当前生效值。清除某项将回落
                  backend/.env 中的默认值。千问文本/生图共用同一个 DashScope API Key。
                </p>
              </>
            ) : (
              <p className="text-sm text-slate-400">设置加载失败，请刷新重试。</p>
            )}

            <Section title="运行状态">
              <StatusRow
                ok={health.status === "ok"}
                label="健康检查"
                value={health.status}
              />
              <StatusRow
                ok={
                  health.llm_provider === "qwen"
                    ? health.has_qwen_llm_credentials
                    : health.has_ark_credentials
                }
                label={`语言模型：${
                  LLM_PROVIDER_OPTIONS.find((o) => o.value === health.llm_provider)
                    ?.label || health.llm_provider
                }`}
                value={
                  health.llm_provider === "qwen"
                    ? health.has_qwen_llm_credentials
                      ? "凭证已配置"
                      : "缺少 DASHSCOPE_API_KEY，调用会失败"
                    : health.has_ark_credentials
                      ? "凭证已配置"
                      : "缺少 ARK_API_KEY / DOUBAO_MODEL，调用会失败"
                }
              />
              <StatusRow
                ok={
                  health.image_provider === "qwen"
                    ? health.has_dashscope_credentials
                    : health.has_credentials
                }
                label={`视觉模型：${
                  IMAGE_PROVIDER_OPTIONS.find((o) => o.value === health.image_provider)
                    ?.label || health.image_provider
                }`}
                value={
                  health.image_provider === "qwen"
                    ? health.has_dashscope_credentials
                      ? "凭证已配置"
                      : "缺少 DASHSCOPE_API_KEY，生成会失败"
                    : health.has_credentials
                      ? "凭证已配置"
                      : "缺少火山引擎 AK/SK，生成会失败"
                }
              />
              <StatusRow
                ok={health.rag_enabled}
                label="RAG 知识库"
                value={health.rag_enabled ? "已启用" : "未启用"}
              />
            </Section>
          </div>
        ) : null}
      </div>
    </main>
  );
}

function ProviderSelect({
  label,
  options,
  value,
  disabled,
  onChange,
}: {
  label: string;
  options: readonly { value: string; label: string }[];
  value: string;
  disabled: boolean;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-2">
      <span className="text-xs font-medium text-slate-600">{label}</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="w-56 rounded-md border border-line bg-white px-3 py-1.5 text-xs text-slate-700 focus:border-blue-400 focus:outline-none"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function SettingField({
  item,
  draft,
  resetting,
  onDraftChange,
  onReset,
}: {
  item: SettingItem;
  draft: string;
  resetting: boolean;
  onDraftChange: (v: string) => void;
  onReset: () => void;
}) {
  const isSecret = SECRET_SETTING_KEYS.has(item.key);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <label className="text-xs font-medium text-slate-600">
          {FIELD_LABELS[item.key] || item.key}
          <code className="ml-2 rounded bg-slate-100 px-1 text-[10px] text-slate-400">
            {item.key}
          </code>
          {item.overridden && (
            <span className="ml-2 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-normal text-blue-600">
              自定义
            </span>
          )}
        </label>
        {item.overridden && (
          <button
            onClick={onReset}
            disabled={resetting}
            title="清除自定义值，回落到 .env 默认"
            className="flex items-center gap-1 text-[11px] text-slate-400 transition-colors hover:text-slate-600 disabled:opacity-50"
          >
            {resetting ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <RotateCcw className="h-3 w-3" />
            )}
            回落 .env
          </button>
        )}
      </div>
      <input
        type={isSecret ? "password" : "text"}
        value={draft}
        onChange={(e) => onDraftChange(e.target.value)}
        placeholder={item.value || "未配置"}
        autoComplete="off"
        className="w-full rounded-md border border-line bg-white px-3 py-1.5 font-mono text-xs text-slate-700 placeholder:font-sans placeholder:text-slate-300 focus:border-blue-400 focus:outline-none"
      />
      {item.overridden && (
        <p className="mt-0.5 text-[10px] text-slate-400">
          .env 默认：{item.env_default || "（空）"}
        </p>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-line bg-white p-5">
      <h2 className="mb-3 text-sm font-semibold text-slate-700">{title}</h2>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function StatusRow({ ok, label, value }: { ok: boolean; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <div className="flex items-center gap-2">
        {ok ? (
          <CheckCircle2 className="h-4 w-4 text-emerald-600" />
        ) : (
          <XCircle className="h-4 w-4 text-red-500" />
        )}
        <span className="text-slate-600">{label}</span>
      </div>
      <span className={`font-medium ${ok ? "text-emerald-700" : "text-red-600"}`}>
        {value}
      </span>
    </div>
  );
}

