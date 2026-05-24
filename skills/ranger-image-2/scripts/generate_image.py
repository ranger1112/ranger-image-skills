#!/usr/bin/env python3
"""Generate an image with gpt-image-2 through an OpenAI-compatible Image API.

Credential resolution order:
1. Environment variables (OPENAI_API_KEY, OPENAI_BASE_URL/CUSTOM_IMAGE_URL)
2. Local Codex config: ~/.codex/ranger-image-2/config.json
3. Interactive prompt with opt-in persistence

The script never prints API keys.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import stat
import sys
import time
from typing import Any, Optional, Tuple
from urllib.parse import urlparse, urlunparse

CONFIG_DIR = Path.home() / ".codex" / "ranger-image-2"
CONFIG_PATH = CONFIG_DIR / "config.json"


def die(message: str, code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def warn(message: str) -> None:
    print(f"Warning: {message}", file=sys.stderr)


def read_config(path: Path = CONFIG_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warn(f"Could not read config file {path}: {exc}")
        return {}
    if not isinstance(data, dict):
        warn(f"Config file {path} is not a JSON object; ignoring it.")
        return {}
    result: dict[str, str] = {}
    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "CUSTOM_IMAGE_URL"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()
    return result


def write_config(values: dict[str, str], path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: v for k, v in values.items() if v}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        # Windows may not fully honor POSIX chmod; the file still lives under the user's profile.
        pass
    print(f"Saved ranger-image-2 config to {path}", file=sys.stderr)


def prompt_yes_no(question: str, *, default: bool = True) -> bool:
    if not sys.stdin.isatty():
        return False
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{question} {suffix} ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def config_is_complete(values: dict[str, str]) -> bool:
    return bool(values.get("OPENAI_API_KEY") and (values.get("OPENAI_BASE_URL") or values.get("CUSTOM_IMAGE_URL")))


def prompt_for_config(existing: dict[str, str], *, persist_complete_noninteractive: bool = False) -> dict[str, str]:
    values = dict(existing)
    if not sys.stdin.isatty():
        if persist_complete_noninteractive and config_is_complete(values):
            write_config(values)
            return values
        die(
            "Missing OPENAI_API_KEY or endpoint, and interactive input is unavailable. "
            "Run with --configure in an interactive terminal, set environment variables before --configure, "
            f"or create {CONFIG_PATH}."
        )

    print("ranger-image-2 needs API configuration.", file=sys.stderr)
    print("Values are saved locally under ~/.codex/ranger-image-2/config.json if you confirm persistence.", file=sys.stderr)

    if not values.get("OPENAI_API_KEY"):
        key = getpass.getpass("OPENAI_API_KEY (input hidden): ").strip()
        if not key:
            die("OPENAI_API_KEY is required.")
        values["OPENAI_API_KEY"] = key

    if not (values.get("OPENAI_BASE_URL") or values.get("CUSTOM_IMAGE_URL")):
        endpoint = input("CUSTOM_IMAGE_URL or OPENAI_BASE_URL: ").strip()
        if not endpoint:
            die("OPENAI_BASE_URL or CUSTOM_IMAGE_URL is required.")
        if endpoint.rstrip("/").endswith("/v1") or "/v1/" in endpoint:
            values["OPENAI_BASE_URL"] = endpoint
        else:
            values["CUSTOM_IMAGE_URL"] = endpoint

    if prompt_yes_no("Persist these values for future ranger-image-2 runs?", default=True):
        write_config(values)
    return values


def resolve_settings(args: argparse.Namespace) -> Tuple[str, Optional[str], Optional[str], str, str]:
    config = read_config()

    key = os.getenv("OPENAI_API_KEY") or config.get("OPENAI_API_KEY")
    explicit_base_url = args.base_url or os.getenv("OPENAI_BASE_URL") or config.get("OPENAI_BASE_URL")
    custom_image_url = os.getenv("CUSTOM_IMAGE_URL") or config.get("CUSTOM_IMAGE_URL")

    if args.configure:
        updated = prompt_for_config({k: v for k, v in {
            "OPENAI_API_KEY": key,
            "OPENAI_BASE_URL": explicit_base_url,
            "CUSTOM_IMAGE_URL": custom_image_url,
        }.items() if v}, persist_complete_noninteractive=True)
        key = updated.get("OPENAI_API_KEY")
        explicit_base_url = args.base_url or updated.get("OPENAI_BASE_URL")
        custom_image_url = updated.get("CUSTOM_IMAGE_URL")

    missing = []
    if not key:
        missing.append("OPENAI_API_KEY")
    if not (explicit_base_url or custom_image_url):
        missing.append("OPENAI_BASE_URL or CUSTOM_IMAGE_URL")
    if missing:
        updated = prompt_for_config({})
        key = key or updated.get("OPENAI_API_KEY")
        explicit_base_url = explicit_base_url or updated.get("OPENAI_BASE_URL")
        custom_image_url = custom_image_url or updated.get("CUSTOM_IMAGE_URL")

    if not key:
        die("OPENAI_API_KEY is not set.")
    base_url = derive_base_url(custom_image_url, explicit_base_url)
    source = "environment" if os.getenv("OPENAI_API_KEY") else "codex-config"
    return key, custom_image_url, explicit_base_url, base_url, source


def derive_base_url(custom_image_url: Optional[str], explicit_base_url: Optional[str]) -> str:
    if explicit_base_url:
        return explicit_base_url.rstrip("/")

    if not custom_image_url:
        die("Set OPENAI_BASE_URL or CUSTOM_IMAGE_URL, or run with --configure.")

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
    if args.configure:
        return "configuration only"
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
    parser.add_argument("--configure", action="store_true", help="Prompt for missing API settings and save them under ~/.codex/ranger-image-2/config.json")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    prompt = read_prompt(args)
    key, _custom_image_url, _explicit_base_url, base_url, config_source = resolve_settings(args)

    if args.configure and prompt == "configuration only":
        print("Configuration complete.")
        return 0

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
        "config_source": config_source,
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
