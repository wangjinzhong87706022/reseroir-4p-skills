"""
vision_extract.py — 离线 VLM 图像识别与交叉校验

从 config.VISION_SOURCES 读取图像，通过 VLM 端点识别数值，
与 config.TEXTUALIZED_VALUES 做交叉校验，结果写入 out/vision/。
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

# 放在 ragflow_import/ 下，config.py 在同一级目录
sys.path.insert(0, str(Path(__file__).parent))
from config import VISION_SOURCES, ORIGINALS_ROOT, OUT_DIR, TEXTUALIZED_VALUES  # type: ignore[attr-defined, assignment]

import requests


# ---------------------------------------------------------------------------
# 公共接口
# ---------------------------------------------------------------------------

def build_payload(image_bytes: bytes, prompt: str) -> dict:
    """
    构建 OpenAI Vision 兼容的 multi-part message payload。

    Returns
    -------
    dict
        ``{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,<b64>"}},
                                        {"type": "text",     "text":     <prompt>}]}``
    """
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return {
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": prompt},
        ],
    }


def call_vision(
    payload: dict,
    endpoint: str,
    api_key: str,
    transport=requests.post,
) -> str:
    """
    向 VLM 端点发送 chat/completions 请求并返回 assistant 消息文本。

    Parameters
    ----------
    payload : dict
        OpenAI-compatible chat completion payload (含 base64 图像).
    endpoint : str
        API base URL，例如 ``"http://localhost:9380/api/v1"``.
    api_key : str
        Bearer token.
    transport : callable, optional
        HTTP transport callable (默认为 ``requests.post``)，用于单元测试注入 mock.

    Returns
    -------
    str
        ``response["choices"][0]["message"]["content"]``.

    Raises
    ------
    requests.HTTPError
        当 HTTP 状态码非 2xx 时.
    """
    url = endpoint.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = transport(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def cross_check(vlm_text: str) -> dict:
    """
    用已知的文本化数值对 VLM 识别结果做交叉校验。

    Parameters
    ----------
    vlm_text : str
        VLM 原始输出文本.

    Returns
    -------
    dict
        ``{"found": {<key>: <bool>}, "values": {<key>: <matched_str>}}``。
        ``found`` 标记每个数值 key（"1454" / "2218" / "788.5"）是否在 vlm_text 中出现；
        ``values`` 把命中的原始子串记录下来（未命中则为空字符串）。
    """
    # 数值 key → (在 vlm_text 中的 substring, 完整的 textualized value)
    numeric_keys = {
        "1454":  ("1454",  "1454 m³/s"),
        "2218":  ("2218",  "2218 m³/s"),
        "788.5": ("788.5", "788.5 m"),
    }

    found: dict[str, bool] = {}
    values: dict[str, str] = {}

    for num_key, (substring, textualized) in numeric_keys.items():
        # 1) 检查数值子串是否出现
        sub_hit = substring in vlm_text
        # 2) 检查完整的 textualized 值（数值+单位）是否出现
        full_hit = textualized in vlm_text

        hit = sub_hit or full_hit

        if full_hit:
            matched = textualized
        elif sub_hit:
            matched = substring
        else:
            matched = ""

        found[num_key] = hit
        values[num_key] = matched

    return {"found": found, "values": values}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="桃曲坡 VLM 图像识别与交叉校验")
    parser.add_argument("--approve", action="store_true", help="创建 approved.flag 并退出")
    parser.add_argument(
        "--limit", type=int, default=0, help="最多处理 N 张图片，0 表示不限制"
    )
    args = parser.parse_args()

    vision_dir = OUT_DIR / "vision"
    vision_dir.mkdir(parents=True, exist_ok=True)

    # --- approve 路径：直接写 flag 文件并退出 ---
    if args.approve:
        (vision_dir / "approved.flag").touch()
        print(f"approved.flag 已创建于 {vision_dir}/approved.flag")
        return

    # --- 检查是否已 approve（跳过所有 VLM 调用）---
    approved_flag = vision_dir / "approved.flag"
    already_approved = approved_flag.exists()

    results: list[dict] = []

    sources = VISION_SOURCES[: args.limit] if args.limit else VISION_SOURCES

    for relative_path, name in sources:
        raw_path = vision_dir / f"{name}_raw.txt"
        cross_path = vision_dir / f"{name}_cross_check.json"
        fail_path = vision_dir / f"{name}_failed.txt"

        # 已 approve 时复用已有输出
        if already_approved:
            if raw_path.exists():
                vlm_text = raw_path.read_text(encoding="utf-8").strip()
            else:
                print(f"[跳过] {name}：approved 模式但缺少 {raw_path}")
                continue
        else:
            # 读取图像并调用 VLM（最多重试 2 次）
            img_file = ORIGINALS_ROOT / relative_path
            if not img_file.exists():
                print(f"[错误] 图像文件不存在: {img_file}")
                fail_path.write_text(f"Image file not found: {img_file}", encoding="utf-8")
                continue

            image_bytes = img_file.read_bytes()
            prompt = "请识别图中所有数值，包括：水位(m)、库容(万m³)、泄量(m³/s)等"
            payload = build_payload(image_bytes, prompt)

            # 读取 API 配置（fallback 到 config 中的默认值）
            endpoint = getattr(sys.modules[__name__], "API_BASE", "http://localhost:9380/api/v1")
            # 从 config 拿 API_BASE（config 模块已经在上面 import 时加载）
            from config import API_BASE as _cfg_endpoint
            endpoint = _cfg_endpoint

            api_key = getattr(sys.modules[__name__], "RAGFLOW_API_KEY", "placeholder")
            from config import RAGFLOW_EMAIL, RAGFLOW_PASSWORD
            import hashlib, time
            # 简单 token：email:password 的 SHA1 前16位作为占位 api_key
            api_key = hashlib.sha1(f"{RAGFLOW_EMAIL}:{RAGFLOW_PASSWORD}".encode()).hexdigest()[:16]

            vlm_text = ""
            for attempt in range(3):  # 0,1,2 → 最多 3 次（原始+2次重试）
                try:
                    vlm_text = call_vision(payload, endpoint, api_key)
                    break
                except Exception as exc:
                    print(f"[警告] {name} 调用失败（第 {attempt+1}/3 次）: {exc}")
                    if attempt == 2:
                        fail_path.write_text(str(exc), encoding="utf-8")
                        vlm_text = ""
                    else:
                        time.sleep(2 ** attempt)  # 指数退避

            if vlm_text:
                raw_path.write_text(vlm_text, encoding="utf-8")

        # cross_check（即使 vlm_text 为空也跑，found 全为 False）
        result = cross_check(vlm_text) if vlm_text else {"found": {}, "values": {}}
        for k in TEXTUALIZED_VALUES:
            if k not in result["found"]:
                result["found"][k] = False
                result["values"][k] = ""

        results.append({"name": name, "result": result})
        cross_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # --- 生成 compare_report.md ---
    lines = ["# VLM 交叉校验报告\n"]
    all_ok = True
    for entry in results:
        name = entry["name"]
        res = entry["result"]
        lines.append(f"## {name}\n")
        for key, textualized in TEXTUALIZED_VALUES.items():
            hit = res["found"].get(key, False)
            val = res["values"].get(key, "")
            status = "OK" if hit else "MISSING"
            lines.append(f"- [{status}] **{key}** (`{textualized}`) → matched: `{val}`")
            if not hit:
                all_ok = False
        lines.append("")

    lines.append("\n---\n*运行前请先人工审查 VLM raw 输出，再用 `--approve` 标记审核通过。*\n")
    report_path = vision_dir / "compare_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    # --- 打印摘要 ---
    ok_count = sum(1 for r in results if all(r["result"]["found"].get(k, False) for k in TEXTUALIZED_VALUES))
    print(f"\n[{ok_count}/{len(results)}] 图片通过交叉校验")
    print(f"报告已写入: {report_path}")
    if already_approved:
        print("(已 approved，跳过 VLM 调用，使用已有输出)")
    if not all_ok:
        print("注意: 部分数值未找到，请人工审查。")


if __name__ == "__main__":
    main()
