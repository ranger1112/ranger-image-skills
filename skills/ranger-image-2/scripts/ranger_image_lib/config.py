"""Configuration and endpoint resolution for ranger-image-2."""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import stat
import sys
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse

from .common import die, warn

CONFIG_DIR = Path.home() / ".codex" / "ranger-image-2"
CONFIG_PATH = CONFIG_DIR / "config.json"


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


def derive_base_url(custom_image_url: Optional[str], explicit_base_url: Optional[str]) -> str:
    if explicit_base_url:
        return explicit_base_url.rstrip("/")

    if not custom_image_url:
        die("Set OPENAI_BASE_URL or CUSTOM_IMAGE_URL, or run with --configure.")

    raw = custom_image_url.rstrip("/")
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        die(f"CUSTOM_IMAGE_URL is not a valid absolute URL: {raw}")

    if "/api/" in parsed.path:
        return urlunparse((parsed.scheme, parsed.netloc, "/v1", "", "", "")).rstrip("/")
    if parsed.path.endswith("/v1") or parsed.path == "/v1":
        return raw
    if parsed.path.endswith("/v1/images/generations"):
        return raw[: -len("/images/generations")]
    return urlunparse((parsed.scheme, parsed.netloc, "/v1", "", "", "")).rstrip("/")


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
