#!/usr/bin/env python3
"""Generate an image with gpt-image-2 through an OpenAI-compatible Image API.

Reads credentials from environment by default and never prints API keys.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse


def die(message: str, code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def derive_base_url(custom_image_url: Optional[str], explicit_base_url: Optional[str]) -> str:
    if explicit_base_url:
        return explicit_base_url.rstrip("/")

    env_base = os.getenv("OPENAI_BASE_URL")
    if env_base:
        return env_base.rstrip("/")

    if not custom_image_url:
        die("Set OPENAI_BASE_URL or CUSTOM_IMAGE_URL. For this workspace, CUSTOM_IMAGE_URL may be https://.../api/image/generate.")

    raw = custom_image_url.rstrip("/")
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        die(f"CUSTOM_IMAGE_URL is not a valid absolute URL: {raw}")

    # Observed workspace behavior: /api/image/generate returned 404, while the same host served
    # OpenAI-compatible routes under /v1. Preserve origin and normalize to /v1.
    if "/api/" in parsed.path:
        return urlunparse((parsed.scheme, parsed.netloc, "/v1", "", "", "")).rstrip("/")
    if parsed.path.endswith("/v1") or parsed.path == "/v1":
        return raw
    if parsed.path.endswith("/v1/images/generations"):
        return raw[: -len("/images/generations")]
    return urlunparse((parsed.scheme, parsed.netloc, "/v1", "", "", "")).rstrip("/")


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt and args.prompt_file:
        die("Use --prompt or --prompt-file, not both.")
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8").strip()
    if args.prompt:
        return args.prompt.strip()
    die("Missing prompt. Use --prompt or --prompt-file.")


def item_get(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def extract_image_bytes(result: Any) -> bytes:
    data = item_get(result, "data")
    if not data:
        die("Image API response did not include data[].")
    first = data[0]
    b64 = item_get(first, "b64_json") or item_get(first, "base64")
    if not b64:
        # Keep this intentionally narrow; URL outputs vary and often need auth/download policy.
        url = item_get(first, "url")
        if url:
            die("Image API returned a URL instead of base64. Re-run with a provider that returns b64_json, or extend this script for URL downloads.")
        die("Image API response did not include data[0].b64_json.")
    if isinstance(b64, str) and b64.lstrip().startswith("data:") and "," in b64:
        b64 = b64.split(",", 1)[1]
    return base64.b64decode(b64)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate images with gpt-image-2 through an OpenAI-compatible Image API")
    parser.add_argument("--prompt")
    parser.add_argument("--prompt-file")
    parser.add_argument("--out", default="output/imagegen/output.png")
    parser.add_argument("--model", default="gpt-image-2")
    parser.add_argument("--size", default="1536x1024")
    parser.add_argument("--quality", default="high")
    parser.add_argument("--output-format", default="png")
    parser.add_argument("--base-url", help="Override OPENAI_BASE_URL/CUSTOM_IMAGE_URL derivation")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    key = os.getenv("OPENAI_API_KEY")
    if not key and not args.dry_run:
        die("OPENAI_API_KEY is not set.")

    prompt = read_prompt(args)
    base_url = derive_base_url(os.getenv("CUSTOM_IMAGE_URL"), args.base_url)
    out = Path(args.out)
    if out.exists() and not args.force:
        die(f"Output already exists: {out} (use --force to overwrite)")

    request_preview = {
        "base_url": base_url,
        "endpoint": "/v1/images/generations",
        "model": args.model,
        "size": args.size,
        "quality": args.quality,
        "output_format": args.output_format,
        "out": str(out),
        "has_api_key": bool(key),
    }
    if args.dry_run:
        print(json.dumps(request_preview, ensure_ascii=False, indent=2))
        return 0

    try:
        from openai import OpenAI
    except ImportError:
        die("openai SDK is not installed. Install with: python -m pip install openai")

    print(json.dumps(request_preview, ensure_ascii=False), file=sys.stderr)
    print("Calling Image API. This can take a couple of minutes.", file=sys.stderr)
    started = time.time()
    client = OpenAI(api_key=key, base_url=base_url)
    result = client.images.generate(
        model=args.model,
        prompt=prompt,
        size=args.size,
        quality=args.quality,
        output_format=args.output_format,
    )
    image = extract_image_bytes(result)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image)
    print(f"Wrote {out}")
    print(f"Generation completed in {time.time() - started:.1f}s.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
