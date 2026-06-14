"""CLI orchestration for ranger-image-2."""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlparse

from .api import call_image_edit_with_local_files, call_image_edit_with_urls, call_image_generation
from .common import die
from .config import resolve_settings
from .output import (
    download_image_url,
    ensure_can_write,
    normalize_image_response,
    output_path_for_index,
    resolve_response_json_path,
    save_response_json,
    url_sidecar_path_for_out,
    write_url_sidecar,
)

DEFAULT_IMAGE_SIZE = "1536x1024"
PRESET_SIZES = {
    "square": "1024x1024",
    "landscape": "1536x1024",
    "portrait": "1024x1536",
    "4k-landscape": "3840x2160",
    "4k-portrait": "2160x3840",
}
SIZE_PATTERN = re.compile(r"^(\d+)x(\d+)$")


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


def resolve_size(size: str | None, preset: str | None) -> str:
    if size and preset:
        die("Use --size or --preset, not both.")
    resolved = PRESET_SIZES[preset] if preset else (size or DEFAULT_IMAGE_SIZE)
    if resolved == "auto":
        return resolved
    match = SIZE_PATTERN.match(resolved)
    if not match or int(match.group(1)) <= 0 or int(match.group(2)) <= 0:
        die("--size must be WIDTHxHEIGHT with positive integers, or use --preset.")
    return resolved


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate or edit images with gpt-image-2 through an OpenAI-compatible Image API")
    parser.add_argument("--prompt")
    parser.add_argument("--prompt-file")
    parser.add_argument("--out", default="output/imagegen/output.png")
    parser.add_argument("--model", default="gpt-image-2")
    parser.add_argument("--size", help=f"Image size as WIDTHxHEIGHT. Default: {DEFAULT_IMAGE_SIZE}")
    parser.add_argument("--preset", choices=sorted(PRESET_SIZES), help="Named size preset. Conflicts with --size")
    parser.add_argument("--quality", default="high")
    parser.add_argument("--output-format", default="png")
    parser.add_argument("--response-format", choices=["b64_json", "url"], help="Ask the provider for b64_json or url responses when supported")
    parser.add_argument("--n", type=int, default=1, help="Number of images to request; saves additional files as name-2.ext, name-3.ext, ...")
    parser.add_argument("--save-response-json", nargs="?", const="auto", help="Save the raw Image API response JSON. Omit value to save next to --out")
    parser.add_argument("--max-download-bytes", type=int, default=50 * 1024 * 1024, help="Maximum bytes to download when the API returns image URLs")
    parser.add_argument("--no-download-url", action="store_true", help="When the API returns image URLs, save .url.txt sidecar files instead of downloading")
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
    return parser


def validate_common_args(args: argparse.Namespace) -> None:
    if args.n < 1:
        die("--n must be >= 1")
    if args.max_download_bytes < 1:
        die("--max-download-bytes must be >= 1")
    if args.timeout < 1:
        die("--timeout must be >= 1")
    args.size = resolve_size(args.size, args.preset)
    validate_edit_args(args)


def call_image_api(key: str, base_url: str, args: argparse.Namespace, prompt: str):
    if args.edit:
        if args.image_url:
            return call_image_edit_with_urls(key=key, base_url=base_url, args=args, prompt=prompt)
        return call_image_edit_with_local_files(key=key, base_url=base_url, args=args, prompt=prompt)
    return call_image_generation(key=key, base_url=base_url, args=args, prompt=prompt)


def expected_paths_for_request(out: Path, args: argparse.Namespace, response_json_path: Path | None) -> list[Path]:
    paths = [
        (
            url_sidecar_path_for_out(output_path_for_index(out, index, args.n))
            if args.no_download_url
            else output_path_for_index(out, index, args.n)
        )
        for index in range(args.n)
    ]
    if response_json_path:
        paths.append(response_json_path)
    return paths


def write_paths_for_entries(entries, out: Path, args: argparse.Namespace) -> list[Path]:
    actual_paths = [output_path_for_index(out, index, len(entries)) for index in range(len(entries))]
    return [
        url_sidecar_path_for_out(path) if entry["kind"] == "url" and args.no_download_url else path
        for path, entry in zip(actual_paths, entries)
    ]


def save_image_entries(entries, out: Path, args: argparse.Namespace) -> None:
    actual_paths = [output_path_for_index(out, index, len(entries)) for index in range(len(entries))]
    ensure_can_write(write_paths_for_entries(entries, out, args), force=args.force)

    for index, entry in enumerate(entries):
        image_out = actual_paths[index]
        if entry["kind"] == "base64":
            image = base64.b64decode(entry["value"])
            image_out.parent.mkdir(parents=True, exist_ok=True)
            image_out.write_bytes(image)
            print(f"Wrote {image_out}")
            continue

        if args.no_download_url:
            write_url_sidecar(url_sidecar_path_for_out(image_out), entry["value"])
            continue

        print(f"Downloading image URL for item {index + 1}/{len(entries)}.", file=sys.stderr)
        image = download_image_url(entry["value"], max_bytes=args.max_download_bytes, timeout=args.timeout)
        image_out.parent.mkdir(parents=True, exist_ok=True)
        image_out.write_bytes(image)
        print(f"Wrote {image_out}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_common_args(args)

    prompt = read_prompt(args)
    key, _custom_image_url, _explicit_base_url, base_url, config_source = resolve_settings(args)

    if args.configure and prompt == "configuration only":
        print("Configuration complete.")
        return 0

    out = Path(args.out)
    response_json_path = resolve_response_json_path(args.save_response_json, out)
    ensure_can_write(expected_paths_for_request(out, args, response_json_path), force=args.force)

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
        "no_download_url": args.no_download_url,
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
    result = call_image_api(key, base_url, args, prompt)
    entries = normalize_image_response(result)
    final_paths = write_paths_for_entries(entries, out, args)
    if response_json_path:
        final_paths.append(response_json_path)
    ensure_can_write(final_paths, force=args.force)

    if response_json_path:
        save_response_json(result, response_json_path)

    save_image_entries(entries, out, args)
    print(f"Generation completed in {time.time() - started:.1f}s.", file=sys.stderr)
    return 0
