#!/usr/bin/env python3
"""Generate or edit images with gpt-image-2 through an OpenAI-compatible Image API."""
from __future__ import annotations

from ranger_image_lib.api import (
    build_common_image_request_args,
    call_image_edit_with_local_files,
    call_image_edit_with_urls,
    call_image_generation,
    can_call_sdk_method,
    endpoint_url,
    post_json,
)
from ranger_image_lib.cli import (
    build_parser,
    call_image_api,
    main,
    read_prompt,
    validate_common_args,
    validate_edit_args,
    validate_http_urls,
    validate_local_files,
)
from ranger_image_lib.common import die, item_get, to_jsonable, warn
from ranger_image_lib.config import (
    config_is_complete,
    derive_base_url,
    prompt_for_config,
    prompt_yes_no,
    read_config,
    resolve_settings,
    write_config,
)
from ranger_image_lib.output import (
    download_image_url,
    ensure_can_write,
    extract_image_entries,
    normalize_image_response,
    output_path_for_index,
    resolve_response_json_path,
    response_json_path_for_out,
    save_response_json,
    strip_data_url_prefix,
    url_sidecar_path_for_out,
    write_url_sidecar,
)

__all__ = [
    "build_common_image_request_args",
    "build_parser",
    "call_image_api",
    "call_image_edit_with_local_files",
    "call_image_edit_with_urls",
    "call_image_generation",
    "can_call_sdk_method",
    "config_is_complete",
    "derive_base_url",
    "die",
    "download_image_url",
    "endpoint_url",
    "ensure_can_write",
    "extract_image_entries",
    "item_get",
    "main",
    "normalize_image_response",
    "output_path_for_index",
    "post_json",
    "prompt_for_config",
    "prompt_yes_no",
    "read_config",
    "read_prompt",
    "resolve_response_json_path",
    "resolve_settings",
    "response_json_path_for_out",
    "save_response_json",
    "strip_data_url_prefix",
    "to_jsonable",
    "url_sidecar_path_for_out",
    "validate_common_args",
    "validate_edit_args",
    "validate_http_urls",
    "validate_local_files",
    "warn",
    "write_config",
    "write_url_sidecar",
]


if __name__ == "__main__":
    raise SystemExit(main())
