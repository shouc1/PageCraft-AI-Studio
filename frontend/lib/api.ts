/** 后端 API 客户端 + WebSocket 辅助。 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

/** 后端任务数据结构。 */
export type Task = {
  id: string;
  user_prompt: string;
  workflow: string;
  status: string;
  progress: number;
  input_image: string | null;
  result_image: string | null;
  expanded_prompt: string | null;
  error_message: string | null;
  session_id: string | null;
  parent_task_id: string | null;
  kind: string;
  image_index: number | null;
  sku: string | null;
  consistency: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

/** 查询单个任务。 */
export async function getTask(id: string): Promise<Task> {
  const res = await fetch(`${API_BASE}/api/tasks/${id}`);
  if (!res.ok) throw new Error(`getTask failed: ${res.status}`);
  return res.json();
}

/** 上传图片，返回后端文件名和访问 URL。 */
export async function uploadImage(
  file: File
): Promise<{ filename: string; url: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/uploads`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(`uploadImage failed: ${res.status}`);
  return res.json();
}

/** 把后端返回的图片路径（如 /api/results/xxx.png）转成完整 URL。 */
export function getImageUrl(path: string | null): string | null {
  if (!path) return null;
  if (path.startsWith("http")) return path;
  if (!path.startsWith("/")) return `${API_BASE}/api/uploads/${path}`;
  return `${API_BASE}${path}`;
}

/** 下载单张图片：fetch 转 Blob 后触发浏览器保存（CORS 已在后端图片接口放开）。 */
export async function downloadImage(url: string, filename: string): Promise<void> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`下载失败（HTTP ${res.status}）`);
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}

/** 从图片路径提取扩展名（默认 png）。 */
export function imageExt(path: string): string {
  const m = path.match(/\.(png|jpe?g|webp)$/i);
  return m ? m[1].toLowerCase() : "png";
}

/** 批量下载：逐张触发保存，filenameOf 返回每张的保存文件名。逐张下载失败不阻断其余。 */
export async function downloadImages(
  items: { path: string; filenameOf: () => string }[]
): Promise<{ ok: number; failed: number }> {
  let ok = 0;
  let failed = 0;
  for (const item of items) {
    const url = getImageUrl(item.path);
    if (!url) {
      failed += 1;
      continue;
    }
    try {
      await downloadImage(url, item.filenameOf());
      ok += 1;
    } catch {
      failed += 1;
    }
    // 浏览器对连续触发的下载有节流，间隔 300ms 保证每张都能弹出
    await new Promise((r) => setTimeout(r, 300));
  }
  return { ok, failed };
}

// ─── 商品会话（需求 v2 §6.4）────────────────────────

export type SellingPoint = {
  point: string;
  visual_concept: string;
};

export type Session = {
  id: string;
  name: string;
  category: string;
  images: string[];
  selling_points: SellingPoint[];
  style: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type CategoryResult = {
  category: string;
  confidence: number;
  candidates: { category: string; confidence: number }[];
  need_confirm: boolean;
};

export type SellingPointsResult = {
  category: string;
  selling_points: SellingPoint[];
};

export type SessionPatch = {
  name?: string;
  category?: string;
  selling_points?: SellingPoint[];
  style?: string;
  images?: string[];
};

export type GenerateImagesParams = {
  prompts: string[];
  kind?: "main_image" | "detail_image";
  workflow?: string | null;
  platform?: string | null;
  skus?: string[];
};

export type GenerateImagesResponse = {
  status: string;
  parent_task_id: string;
  subtask_ids: string[];
  count: number;
};

/** 带 HTTP 状态码的 API 错误：status=0 表示网络层失败（后端未启动/断网等）。 */
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(status === 0 ? detail : `API ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** 通用请求封装：会话族接口统一错误处理。 */
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${url}`, init);
  } catch {
    // fetch 网络层异常（连接拒绝 / DNS 失败 / 断网）
    throw new ApiError(0, "无法连接后端服务");
  }
  if (!res.ok) {
    // 优先取 FastAPI 的 {"detail": "..."} 结构，退化取原始文本
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body);
    } catch {
      detail = await res.text().catch(() => "");
    }
    throw new ApiError(res.status, detail || res.statusText);
  }
  return res.json();
}

export async function listSessions(limit = 50): Promise<Session[]> {
  return request<Session[]>(`/api/sessions?limit=${limit}`);
}

export async function getSession(id: string): Promise<Session> {
  return request<Session>(`/api/sessions/${id}`);
}

export async function createSession(body: {
  name?: string;
  images?: string[];
}): Promise<Session> {
  return request<Session>("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: body.name || "", images: body.images || [] }),
  });
}

export async function updateSession(
  id: string,
  patch: SessionPatch
): Promise<Session> {
  return request<Session>(`/api/sessions/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

export async function deleteSession(id: string): Promise<void> {
  await request<{ status: string }>(`/api/sessions/${id}`, { method: "DELETE" });
}

export async function categorizeSession(
  id: string,
  userHint = ""
): Promise<CategoryResult> {
  return request<CategoryResult>(`/api/sessions/${id}/categorize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_hint: userHint }),
  });
}

export async function extractSellingPoints(
  id: string,
  userHint = ""
): Promise<SellingPointsResult> {
  return request<SellingPointsResult>(`/api/sessions/${id}/selling-points`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_hint: userHint }),
  });
}

export async function generateMainImages(
  id: string,
  params: GenerateImagesParams
): Promise<GenerateImagesResponse> {
  return request<GenerateImagesResponse>(`/api/sessions/${id}/main-images`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompts: params.prompts,
      kind: params.kind || "main_image",
      workflow: params.workflow || null,
      platform: params.platform || null,
      skus: params.skus || [],
    }),
  });
}

export async function regenerateTask(
  taskId: string
): Promise<{ status: string; task_id: string }> {
  return request<{ status: string; task_id: string }>(
    `/api/tasks/${taskId}/regenerate`,
    { method: "POST" }
  );
}

// ─── 详情页生成（需求 v2 F-D）────────────────────────

export type DetailSlot = {
  index: number;
  slot: string;
  desc: string;
  prompt_hint: string;
};

export type DetailPlanResult = {
  category: string;
  slots: DetailSlot[];
};

export async function getDetailPlan(id: string): Promise<DetailPlanResult> {
  return request<DetailPlanResult>(`/api/sessions/${id}/detail-plan`);
}

export async function generateDetailImages(
  id: string,
  params: GenerateImagesParams
): Promise<GenerateImagesResponse> {
  return request<GenerateImagesResponse>(`/api/sessions/${id}/detail-images`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompts: params.prompts,
      kind: params.kind || "detail_image",
      workflow: params.workflow || null,
      platform: params.platform || null,
      skus: params.skus || [],
    }),
  });
}

// ─── 营销文案生成（需求 v2 F-C）────────────────────────

export type CopyIssue = {
  field: string;
  word: string;
  suggestion: string;
  count: number;
};

export type CopywritingPlan = {
  type: string;
  title: string;
  main_copy: string;
  detail_copy: string;
  issues: CopyIssue[];
};

export type Hotspot = {
  name: string;
  hint: string;
  type: string;
  days_until: number;
};

export type CopywritingResult = {
  category: string;
  plans: CopywritingPlan[];
  hotspots: Hotspot[];
};

export async function generateCopywriting(
  id: string,
  userHint = ""
): Promise<CopywritingResult> {
  return request<CopywritingResult>(`/api/sessions/${id}/copywriting`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_hint: userHint }),
  });
}

// ─── 风格库管理（需求 v2 F-M3 风格库用户可感知层）────────

export type StyleEntry = {
  name: string;
  source: string;
  products: string;
  colors: string;
  elements: string;
  lighting: string;
  background: string;
  composition: string;
  prompt_template: string;
  negative_prompt: string;
  recommended: boolean;
};

export type StyleListResponse = {
  total: number;
  rag_enabled: boolean;
  styles: StyleEntry[];
};

export type StylePatch = Partial<
  Pick<
    StyleEntry,
    | "products"
    | "colors"
    | "elements"
    | "lighting"
    | "background"
    | "composition"
    | "prompt_template"
    | "negative_prompt"
  >
>;

/** 风格库列表；带 query 时 RAG 推荐前 topK 置顶并标记 recommended（会话内风格选择用）。 */
export async function listStyles(
  query = "",
  topK = 3
): Promise<StyleListResponse> {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("query", query.trim());
    params.set("top_k", String(topK));
  }
  const qs = params.toString();
  return request<StyleListResponse>(`/api/styles${qs ? `?${qs}` : ""}`);
}

/** 编辑风格条目（字段级更新，风格名不可改），返回更新后的条目。 */
export async function updateStyle(
  name: string,
  patch: StylePatch
): Promise<StyleEntry> {
  const res = await request<{
    status: string;
    style: StyleEntry;
    index_rebuild: string;
  }>(`/api/styles/${encodeURIComponent(name)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return res.style;
}

// ─── 运行时设置（DB 覆盖层 > .env，改后即时生效）───────────

export type SettingItem = {
  key: string;
  /** 生效值；密钥类字段为脱敏值（首尾 4 位保留） */
  value: string;
  /** true 表示 DB 覆盖中；false 表示来自 .env 默认 */
  overridden: boolean;
  /** .env 出厂默认值（密钥脱敏） */
  env_default: string;
};

export type SettingsOverview = {
  has_credentials: boolean;
  has_ark_credentials: boolean;
  has_dashscope_credentials: boolean;
  has_qwen_llm_credentials: boolean;
  llm_provider: string;
  image_provider: string;
  settings: SettingItem[];
};

/** 密钥类设置键：输入框用 password 型展示 */
export const SECRET_SETTING_KEYS = new Set([
  "ARK_API_KEY",
  "VOLCENGINE_AK",
  "VOLCENGINE_SK",
  "DASHSCOPE_API_KEY",
]);

/** 语言模型厂商选项（LLM_PROVIDER 下拉） */
export const LLM_PROVIDER_OPTIONS = [
  { value: "doubao", label: "豆包（火山引擎 ARK）" },
  { value: "qwen", label: "千问（阿里云百炼）" },
] as const;

/** 视觉模型厂商选项（IMAGE_PROVIDER 下拉） */
export const IMAGE_PROVIDER_OPTIONS = [
  { value: "jimeng", label: "即梦 AI（火山引擎）" },
  { value: "qwen", label: "千问（阿里云百炼）" },
] as const;

export function getSettings(): Promise<SettingsOverview> {
  return request<SettingsOverview>("/api/settings");
}

/** 部分更新设置：只传要改的键；值传空字符串表示清除覆盖、回落 .env。 */
export function updateSettings(
  values: Record<string, string>
): Promise<SettingsOverview> {
  return request<SettingsOverview>("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ values }),
  });
}
