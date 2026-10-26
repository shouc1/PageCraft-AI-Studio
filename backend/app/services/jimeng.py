"""即梦 AI 调用（火山引擎视觉智能 API）。

调真实 API（提交异步任务 → 轮询结果 → 下载图片）；
无密钥或调用失败时直接抛错。
"""

import asyncio
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
import httpx
from app.config import settings
from app.logger import logger
from app.services.jimeng_adapters import build_jimeng_request


# ─── 火山引擎 V4 签名 ──────────────────────────────────────

def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(secret_key: str, date: str, region: str, service: str) -> bytes:
    k_date = _sign(secret_key.encode("utf-8"), date)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "request")
    return k_signing


def _v4_sign(
    method: str,
    base_url: str,
    query_params: dict[str, str],
    body: dict,
    ak: str,
    sk: str,
    region: str,
    service: str,
) -> tuple[str, dict[str, str]]:
    """生成火山引擎 V4 签名，返回 (完整url, 请求头)。"""
    parsed = urlparse(base_url)
    host = parsed.hostname
    path = parsed.path or "/"

    now = datetime.now(timezone.utc)
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    # 所有 query 参数按字母排序
    sorted_query = dict(sorted(query_params.items()))
    canonical_querystring = urlencode(sorted_query)

    body_str = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    payload_hash = hashlib.sha256(body_str.encode("utf-8")).hexdigest()

    canonical_headers = f"host:{host}\nx-date:{x_date}\n"
    signed_headers = "host;x-date"

    canonical_request = (
        f"{method}\n"
        f"{path}\n"
        f"{canonical_querystring}\n"
        f"{canonical_headers}\n"
        f"{signed_headers}\n"
        f"{payload_hash}"
    )

    algorithm = "HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/{service}/request"
    string_to_sign = (
        f"{algorithm}\n"
        f"{x_date}\n"
        f"{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    signing_key = _get_signature_key(sk, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"{algorithm} "
        f"Credential={ak}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    full_url = f"{base_url}?{canonical_querystring}"
    headers = {
        "X-Date": x_date,
        "Authorization": authorization,
    }
    return full_url, headers


async def generate(
    workflow: str,
    prompt: str,
    input_images: list[str] | None = None,
    strength: float | None = None,
    size: str | None = None,
) -> tuple[Path, dict]:
    """调用即梦生成图片，返回结果图片路径。

    Args:
        workflow: image2image / text2image
        prompt: 扩展后的 prompt
        input_images: 参考图文件名列表（image2image 支持多图融合）
        strength: i2i 重绘强度（需求 v2 §5 压低到 0.3~0.5）
        size: 生图尺寸，如 "1024x1024"

    Returns:
        结果图片的本地路径
    """
    if not settings.has_credentials:
        raise RuntimeError("即梦 API 未配置，请检查 VOLCENGINE_AK 和 VOLCENGINE_SK")

    return await _real_generate(workflow, prompt, input_images, strength, size)


# ─── 真实模式 ──────────────────────────────────────────────

async def _real_generate(
    workflow: str,
    prompt: str,
    input_images: list[str] | None,
    strength: float | None,
    size: str | None,
) -> tuple[Path, dict]:
    """调真实即梦 API（V4 签名 + 异步任务 + 轮询）。"""
    ak = settings.volcengine_ak
    sk = settings.volcengine_sk
    region = settings.jimeng_region
    service = settings.jimeng_service
    base_url = settings.jimeng_api_base

    # 读取多参考图 base64（需求 v2 §5 多图融合提升一致性）
    input_images_b64: list[str] = []

    def _resolve_image_path(filename: str) -> Path | None:
        for directory in (settings.upload_dir, settings.result_dir):
            path = directory / filename
            if path.exists():
                return path
        return None

    if input_images:
        for filename in input_images:
            path = _resolve_image_path(filename)
            if path:
                input_images_b64.append(base64.b64encode(path.read_bytes()).decode())

    request = build_jimeng_request(workflow, prompt, input_images_b64 or None, size, strength)

    # 提交任务
    submit_query = {"Action": request.action, "Version": request.version}
    submit_url, submit_headers = _v4_sign(
        "POST", base_url, submit_query, request.body, ak, sk, region, service
    )

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(submit_url, json=request.body, headers=submit_headers)
        if resp.status_code != 200:
            logger.error("即梦提交失败 HTTP %d: %s", resp.status_code, resp.text)
            raise RuntimeError(f"即梦提交失败 HTTP {resp.status_code}: {resp.text}")
        task_data = resp.json()
        if task_data.get("code") != 10000:
            logger.error("即梦提交失败：%s", task_data.get('message', task_data))
            raise RuntimeError(f"即梦提交失败：{task_data.get('message', task_data)}")
        jimeng_task_id = task_data["data"]["task_id"]
        logger.info("即梦任务已提交，task_id=%s", jimeng_task_id)

        # 轮询结果
        result_body = {"req_key": request.body["req_key"], "task_id": jimeng_task_id}
        result_query = {"Action": request.result_action, "Version": request.result_version}

        for _ in range(120):
            await asyncio.sleep(2)
            result_url, result_headers = _v4_sign(
                "POST", base_url, result_query, result_body, ak, sk, region, service
            )
            poll_resp = await client.post(result_url, json=result_body, headers=result_headers)
            if poll_resp.status_code != 200:
                raise RuntimeError(f"即梦查询失败 HTTP {poll_resp.status_code}: {poll_resp.text}")
            poll_data = poll_resp.json()
            if poll_data.get("code") != 10000:
                raise RuntimeError(f"即梦查询失败：{poll_data.get('message', poll_data)}")

            status = poll_data["data"].get("status")
            if status == "done":
                result_path = settings.result_dir / f"result_{jimeng_task_id}.png"

                # 优先用 binary_data_base64（即梦 4.0 直接返回图片 base64）
                b64_list = poll_data["data"].get("binary_data_base64", [])
                if b64_list:
                    img_bytes = base64.b64decode(b64_list[0])
                    result_path.write_bytes(img_bytes)
                    return result_path, {"provider": "jimeng", "provider_task_id": jimeng_task_id}

                # 兼容 image_urls 方式
                image_urls = poll_data["data"].get("image_urls", [])
                if image_urls:
                    img_resp = await client.get(image_urls[0])
                    img_resp.raise_for_status()
                    result_path.write_bytes(img_resp.content)
                    return result_path, {"provider": "jimeng", "provider_task_id": jimeng_task_id}

                raise RuntimeError(f"即梦生成完成但无图片数据：{poll_data['data'].keys()}")
            elif status == "failed":
                raise RuntimeError(f"即梦生成失败：{poll_data['data'].get('message', '')}")

    raise TimeoutError("即梦生成超时")
