#!/usr/bin/env python3
"""Generate or edit images with gpt-image-2 through an OpenAI-compatible Image API.

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
import inspect
import json
import os
from pathlib import Path
import stat
import sys
import time
from typing import Any, Optional, Tuple
import urllib.error
import urllib.request
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
    try:
        answer = input(f"{question} {suffix} ").strip().lower()
    except EOFError:
        return False
    if not answer:
        return default
    return answer in {"y", "yes"}


def config_is_complete(values: dict[str, str]) -> bool:
    return bool(values.get("OPENAI_API_KEY") and (values.get("OPENAI_BASE_URL") or values.get("CUSTOM_IMAGE_URL")))


def prompt_for_config(existing: dict[str, str], *, persist_complete_noninteractive: bool = False) -> dict[str, str]:
    values = dict(existing)
    if persist_complete_noninteractive and config_is_complete(values):
        write_config(values)
        return values

    if not sys.stdin.isatty():
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


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    return value


def save_response_json(result: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote response JSON {path}")


def strip_data_url_prefix(value: str) -> str:
    if value.lstrip().startswith("data:") and "," in value:
        return value.split(",", 1)[1]
    return value


def extract_image_entries(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, (bytes, bytearray)):
        return [{"index": 0, "kind": "base64", "value": base64.b64encode(bytes(result)).decode("ascii")}]

    data = item_get(result, "data")
    if not data:
        die("Image API response did not include data[].")
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        b64 = item_get(item, "b64_json") or item_get(item, "base64")
        url = item_get(item, "url")
        if isinstance(b64, str) and b64.strip():
            entries.append({"index": index, "kind": "base64", "value": strip_data_url_prefix(b64)})
            continue
        if isinstance(url, str) and url.strip():
            if url.lstrip().startswith("data:") and "," in url:
                entries.append({"index": index, "kind": "base64", "value": strip_data_url_prefix(url)})
            else:
                entries.append({"index": index, "kind": "url", "value": url.strip()})
            continue
        die(f"Image API response did not include data[{index}].b64_json or data[{index}].url.")
    return entries


def download_image_url(url: str, *, max_bytes: int, timeout: int) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        die(f"Image URL is not a valid http(s) URL: {url}")

    request = urllib.request.Request(url, headers={"Accept": "image/png,image/jpeg,image/webp,*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        if content_type and not content_type.lower().startswith("image/"):
            warn(f"Downloaded URL content-type is not image/*: {content_type}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                die(f"Downloaded image exceeds --max-download-bytes ({max_bytes}).")
            chunks.append(chunk)
    return b"".join(chunks)


def output_path_for_index(base: Path, index: int, total: int) -> Path:
    if total <= 1 or index == 0:
        return base
    suffix = base.suffix or ".png"
    return base.with_name(f"{base.stem}-{index + 1}{suffix}")


def response_json_path_for_out(out: Path) -> Path:
    return out.with_suffix(out.suffix + ".response.json" if out.suffix else ".response.json")


def resolve_response_json_path(value: Optional[str], out: Path) -> Optional[Path]:
    if value is None:
        return None
    if value == "auto":
        return response_json_path_for_out(out)
    return Path(value)


def ensure_can_write(paths: list[Path], *, force: bool) -> None:
    if force:
        return
    seen: set[Path] = set()
    for path in paths:
        normalized = path.resolve() if path.exists() else path.absolute()
        if normalized in seen:
            continue
        seen.add(normalized)
        if path.exists():
            die(f"Output already exists: {path} (use --force to overwrite)")


def endpoint_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def validate_local_files(paths: list[str], *, label: str) -> None:
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            die(f"{label} does not exist: {path}")
        if not path.is_file():
            die(f"{label} is not a file: {path}")


def validate_http_urls(urls: list[str], *, label: str) -> None:
    for raw in urls:
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            die(f"{label} must be an absolute http(s) URL: {raw}")


def validate_edit_args(args: argparse.Namespace) -> None:
    image_paths = args.image or []
    image_urls = args.image_url or []
    if not args.edit:
        if image_paths or image_urls or args.mask or args.mask_url:
            die("Use --edit when passing --image, --image-url, --mask, or --mask-url.")
        return

    if not image_paths and not image_urls:
        die("--edit requires at least one --image or --image-url.")
    if image_paths and image_urls:
        die("Do not mix local --image files with remote --image-url in one edit request.")
    if args.mask and args.mask_url:
        die("Use --mask or --mask-url, not both.")
    if image_paths and args.mask_url:
        die("--mask-url is only supported with --image-url JSON edit requests; use --mask with local --image files.")
    if image_urls and args.mask:
        die("--mask is only supported with local --image files; use --mask-url with --image-url requests.")

    validate_local_files(image_paths, label="Image")
    if args.mask:
        validate_local_files([args.mask], label="Mask")
    validate_http_urls(image_urls, label="Image URL")
    if args.mask_url:
        validate_http_urls([args.mask_url], label="Mask URL")


def build_common_image_request_args(args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    request_args: dict[str, Any] = {
        "model": args.model,
        "prompt": prompt,
        "size": args.size,
        "quality": args.quality,
        "output_format": args.output_format,
    }
    if args.n != 1:
        request_args["n"] = args.n
    if args.response_format:
        request_args["response_format"] = args.response_format
    return request_args


def can_call_sdk_method(method: Any, request_args: dict[str, Any]) -> bool:
    try:
        sig = inspect.signature(method)
    except Exception:
        return True
    unsupported = [key for key in request_args if key not in sig.parameters]
    if unsupported:
        warn(f"openai SDK method does not expose {', '.join(unsupported)}; falling back to raw HTTP.")
        return False
    return True


def post_json(
    *,
    key: str,
    url: str,
    payload: dict[str, Any],
    timeout: int,
) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read()
    except urllib.error.HTTPError as exc:
        error_body = exc.read(4096).decode("utf-8", errors="replace")
        die(f"Image API returned HTTP {exc.code}: {error_body}")
    except urllib.error.URLError as exc:
        die(f"Image API request failed: {exc.reason}")

    try:
        return json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # Some OpenAI-compatible image providers return the image bytes directly.
        return {"data": [{"base64": base64.b64encode(response_body).decode("ascii")}]}


def call_image_generation(
    *,
    key: str,
    base_url: str,
    args: argparse.Namespace,
    prompt: str,
) -> Any:
    request_args = build_common_image_request_args(args, prompt)
    try:
        from openai import OpenAI
    except ImportError:
        warn("openai SDK is not installed; falling back to raw HTTP.")
    else:
        client = OpenAI(api_key=key, base_url=base_url, timeout=args.timeout)
        if can_call_sdk_method(client.images.generate, request_args):
            return client.images.generate(**request_args)

    return post_json(
        key=key,
        url=endpoint_url(base_url, "/images/generations"),
        payload=request_args,
        timeout=args.timeout,
    )


def call_image_edit_with_urls(
    *,
    key: str,
    base_url: str,
    args: argparse.Namespace,
    prompt: str,
) -> Any:
    image_urls = args.image_url or []
    payload = build_common_image_request_args(args, prompt)
    if len(image_urls) == 1:
        payload["image_url"] = image_urls[0]
    else:
        payload["image_urls"] = image_urls
    if args.mask_url:
        payload["mask_url"] = args.mask_url
    return post_json(
        key=key,
        url=endpoint_url(base_url, "/images/edits"),
        payload=payload,
        timeout=args.timeout,
    )


def call_image_edit_with_local_files(
    *,
    key: str,
    base_url: str,
    args: argparse.Namespace,
    prompt: str,
) -> Any:
    try:
        from openai import OpenAI
    except ImportError:
        die("openai SDK is required for local file edits. Install with: python -m pip install openai")

    client = OpenAI(api_key=key, base_url=base_url, timeout=args.timeout)
    image_handles = []
    mask_handle = None
    try:
        image_handles = [open(path, "rb") for path in (args.image or [])]
        mask_handle = open(args.mask, "rb") if args.mask else None
        request_args = build_common_image_request_args(args, prompt)
        request_args["image"] = image_handles[0] if len(image_handles) == 1 else image_handles
        if mask_handle:
            request_args["mask"] = mask_handle
        return client.images.edit(**request_args)
    finally:
        for handle in image_handles:
            handle.close()
        if mask_handle:
            mask_handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or edit images with gpt-image-2 through an OpenAI-compatible Image API")
    parser.add_argument("--prompt")
    parser.add_argument("--prompt-file")
    parser.add_argument("--out", default="output/imagegen/output.png")
    parser.add_argument("--model", default="gpt-image-2")
    parser.add_argument("--size", default="1536x1024")
    parser.add_argument("--quality", default="high")
    parser.add_argument("--output-format", default="png")
    parser.add_argument("--response-format", choices=["b64_json", "url"], help="Ask the provider for b64_json or url responses when supported")
    parser.add_argument("--n", type=int, default=1, help="Number of images to request; saves additional files as name-2.ext, name-3.ext, ...")
    parser.add_argument("--save-response-json", nargs="?", const="auto", help="Save the raw Image API response JSON. Omit value to save next to --out")
    parser.add_argument("--max-download-bytes", type=int, default=50 * 1024 * 1024, help="Maximum bytes to download when the API returns image URLs")
    parser.add_argument("--edit", action="store_true", help="Call /v1/images/edits instead of /v1/images/generations")
    parser.add_argument("--image", action="append", help="Local source image for --edit. Repeat for multiple images when the provider supports it")
    parser.add_argument("--image-url", action="append", help="Remote source image URL for --edit provider extensions. Repeat for multiple URLs")
    parser.add_argument("--mask", help="Local PNG mask for --edit with local --image files")
    parser.add_argument("--mask-url", help="Remote PNG mask URL for --edit with --image-url")
    parser.add_argument("--base-url", help="Override OPENAI_BASE_URL/CUSTOM_IMAGE_URL derivation")
    parser.add_argument("--configure", action="store_true", help="Prompt for missing API settings and save them under ~/.codex/ranger-image-2/config.json")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=int, default=360, help="Image API request timeout in seconds")
    args = parser.parse_args()

    if args.n < 1:
        die("--n must be >= 1")
    if args.max_download_bytes < 1:
        die("--max-download-bytes must be >= 1")
    if args.timeout < 1:
        die("--timeout must be >= 1")
    validate_edit_args(args)

    prompt = read_prompt(args)
    key, _custom_image_url, _explicit_base_url, base_url, config_source = resolve_settings(args)

    if args.configure and prompt == "configuration only":
        print("Configuration complete.")
        return 0

    out = Path(args.out)
    response_json_path = resolve_response_json_path(args.save_response_json, out)
    expected_paths = [output_path_for_index(out, index, args.n) for index in range(args.n)]
    if response_json_path:
        expected_paths.append(response_json_path)
    ensure_can_write(expected_paths, force=args.force)

    request_preview = {
        "base_url": base_url,
        "endpoint": "/v1/images/edits" if args.edit else "/v1/images/generations",
        "mode": "edit" if args.edit else "generate",
        "model": args.model,
        "n": args.n,
        "size": args.size,
        "quality": args.quality,
        "output_format": args.output_format,
        "response_format": args.response_format or "(provider default)",
        "out": str(out),
        "save_response_json": str(response_json_path) if response_json_path else None,
        "max_download_bytes": args.max_download_bytes,
        "timeout": args.timeout,
        "image_count": len(args.image or []),
        "image_url_count": len(args.image_url or []),
        "has_mask": bool(args.mask or args.mask_url),
        "has_api_key": bool(key),
        "config_source": config_source,
    }
    if args.dry_run:
        print(json.dumps(request_preview, ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(request_preview, ensure_ascii=False), file=sys.stderr)
    print("Calling Image API. This can take a couple of minutes.", file=sys.stderr)
    started = time.time()
    if args.edit:
        if args.image_url:
            result = call_image_edit_with_urls(key=key, base_url=base_url, args=args, prompt=prompt)
        else:
            result = call_image_edit_with_local_files(key=key, base_url=base_url, args=args, prompt=prompt)
    else:
        result = call_image_generation(key=key, base_url=base_url, args=args, prompt=prompt)

    entries = extract_image_entries(result)
    actual_paths = [output_path_for_index(out, index, len(entries)) for index in range(len(entries))]
    final_paths = [*actual_paths, *([response_json_path] if response_json_path else [])]
    ensure_can_write(final_paths, force=args.force)

    if response_json_path:
        save_response_json(result, response_json_path)

    for index, entry in enumerate(entries):
        image_out = actual_paths[index]
        if entry["kind"] == "base64":
            image = base64.b64decode(entry["value"])
        else:
            print(f"Downloading image URL for item {index + 1}/{len(entries)}.", file=sys.stderr)
            image = download_image_url(entry["value"], max_bytes=args.max_download_bytes, timeout=args.timeout)
        image_out.parent.mkdir(parents=True, exist_ok=True)
        image_out.write_bytes(image)
        print(f"Wrote {image_out}")
    print(f"Generation completed in {time.time() - started:.1f}s.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
