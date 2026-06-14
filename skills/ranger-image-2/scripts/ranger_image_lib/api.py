"""OpenAI-compatible Image API callers."""
from __future__ import annotations

import argparse
import base64
import inspect
import json
from typing import Any
import urllib.error
import urllib.request

from .common import die, warn


def endpoint_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


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


def post_json(*, key: str, url: str, payload: dict[str, Any], timeout: int) -> Any:
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


def call_image_generation(*, key: str, base_url: str, args: argparse.Namespace, prompt: str) -> Any:
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


def call_image_edit_with_urls(*, key: str, base_url: str, args: argparse.Namespace, prompt: str) -> Any:
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


def call_image_edit_with_local_files(*, key: str, base_url: str, args: argparse.Namespace, prompt: str) -> Any:
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
