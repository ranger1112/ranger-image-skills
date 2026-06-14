"""Image response normalization and local output helpers."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, TypedDict
import urllib.request
from urllib.parse import urlparse

from .common import die, item_get, to_jsonable, warn


class ImageEntry(TypedDict):
    index: int
    kind: str
    value: str


def save_response_json(result: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote response JSON {path}")


def strip_data_url_prefix(value: str) -> str:
    if value.lstrip().startswith("data:") and "," in value:
        return value.split(",", 1)[1]
    return value


def normalize_image_response(result: Any) -> list[ImageEntry]:
    if isinstance(result, (bytes, bytearray)):
        return [{"index": 0, "kind": "base64", "value": base64.b64encode(bytes(result)).decode("ascii")}]

    data = item_get(result, "data")
    if not data:
        die("Image API response did not include data[].")

    entries: list[ImageEntry] = []
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


# Backward-compatible alias for older ad-hoc imports/tests.
extract_image_entries = normalize_image_response


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


def url_sidecar_path_for_out(out: Path) -> Path:
    return out.with_suffix(out.suffix + ".url.txt" if out.suffix else ".url.txt")


def resolve_response_json_path(value: str | None, out: Path) -> Path | None:
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


def write_url_sidecar(path: Path, url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(url + "\n", encoding="utf-8")
    print(f"Wrote image URL {path}")
