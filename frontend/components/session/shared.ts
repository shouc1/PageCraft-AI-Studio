import type { SellingPoint } from "@/lib/api";

/** 商业级画质兜底要求：所有未经过三专家扩写的 prompt 均依赖此层保证成片质量。 */
const QUALITY_BASELINE = [
  "画质要求：商业级电商摄影，专业棚拍布光，柔和均匀光影",
  "超高清细节，商品表面干净无污渍、无划痕、无指纹",
  "背景整洁无杂物，画面无文字、无水印、无多余 logo",
  "保留商品真实外观与结构比例，主体清晰完整",
].join("，");

/** 由类目 + 卖点 + 风格 + 尾部定位拼接分层 prompt（主体 / 场景构图 / 画质）。
 *
 * 分层结构对齐后端三专家流水线的正向 prompt 四层规范：
 * 模板兜底生成质量下限，三专家扩写在批量任务中进一步提升。
 */
export function composePrompt(
  category: string,
  points: SellingPoint[],
  style: string,
  tail: string
): string {
  const pts = points.map((p) => p.point).filter(Boolean);
  const subject = [
    category ? `${category}商品` : "商品",
    pts.length ? `核心卖点：${pts.join("、")}` : "",
  ]
    .filter(Boolean)
    .join("，");

  const lines: string[] = [`主体：${subject}`];

  const scene = [style ? `${style}风格` : "", tail.trim()]
    .filter(Boolean)
    .join("，");
  if (scene) lines.push(`场景与构图：${scene}`);

  lines.push(QUALITY_BASELINE);
  return lines.join("\n");
}
