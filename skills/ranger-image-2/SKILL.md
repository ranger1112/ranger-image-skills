---
name: ranger-image-2
description: Generate images with gpt-image-2 through an OpenAI-compatible Image API using the current OPENAI_API_KEY, OPENAI_BASE_URL, or CUSTOM_IMAGE_URL environment variables. Use when the user asks to call gpt-image-2 via API/CLI, /v1/images/generations, the prior /api/image/generate endpoint flow, or wants the faster API route instead of Codex CLI image_generation/session extraction.
---

# Ranger Image 2

Use this skill to generate raster images through an OpenAI-compatible Image API with `gpt-image-2`.

## Rules

- Resolve credentials in this order: environment variables first, then `~/.codex/ranger-image-2/config.json`, then interactive `--configure` prompts when a terminal is available.
- Never echo, commit, or write API keys anywhere except the user-local Codex config file after explicit confirmation.
- Prefer `scripts/generate_image.py` instead of hand-writing one-off API callers.
- Use the API route for speed when the user rejects the Codex CLI `--enable image_generation` session-extraction skill as too slow.
- If `CUSTOM_IMAGE_URL` is set to a path such as `https://host/api/image/generate`, normalize the same origin to `https://host/v1` and call `/v1/images/generations`; this workspace observed `/api/image/generate` returning 404 while `/v1` routes worked.
- Keep the user's prompt verbatim unless they ask for prompt polishing.

## One-time configuration

If `OPENAI_API_KEY` plus `OPENAI_BASE_URL` or `CUSTOM_IMAGE_URL` are missing, run:

```powershell
python skills/ranger-image-2/scripts/generate_image.py --configure
```

The script asks for missing values, hides API-key input, and can persist them to:

```text
~/.codex/ranger-image-2/config.json
```

Environment variables always override this local config. Do not commit the config file.

## Quick start

```powershell
python skills/ranger-image-2/scripts/generate_image.py `
  --prompt "Create a sunset afterglow..." `
  --out output/imagegen/sunset.png `
  --size 1536x1024 `
  --quality high `
  --timeout 360 `
  --force
```

Set credentials and endpoint values in the shell environment before running. If `OPENAI_BASE_URL` is already set, the script uses it directly. Otherwise it derives the provider origin plus `/v1` from `CUSTOM_IMAGE_URL`.

## Workflow

1. Run `scripts/generate_image.py --dry-run` for a cheap configuration check.
2. If credentials or endpoint are missing and an interactive terminal is available, run `scripts/generate_image.py --configure` and let the user provide values; persist only after confirmation.
3. Save long prompts to a temporary prompt file to avoid shell quoting issues.
4. Run `scripts/generate_image.py` with `--prompt-file` or `--prompt`, choosing a workspace output path under `output/imagegen/` unless the user specified another path.
5. Validate the saved file: existence, non-zero byte size, and dimensions.

## Validation snippets

PowerShell image dimension check:

```powershell
Add-Type -AssemblyName System.Drawing
$path = 'output/imagegen/result.png'
$item = Get-Item -LiteralPath $path
$img = [System.Drawing.Image]::FromFile((Resolve-Path $path).Path)
try {
  [pscustomobject]@{
    Path = $path
    Bytes = $item.Length
    Dimensions = "$($img.Width)x$($img.Height)"
  } | ConvertTo-Json -Compress
} finally {
  $img.Dispose()
}
```

## Troubleshooting

- `404 page not found` on `/api/image/generate`: use the same host's `/v1/images/generations` route by deriving `OPENAI_BASE_URL=https://host/v1`.
- Older OpenAI SDK versions that do not expose `output_format`: the bundled script automatically falls back to raw `/v1/images/generations`.
- Slow image jobs: increase `--timeout`; the default is 360 seconds.
- TLS errors from raw HTTP fallback: install or upgrade the OpenAI SDK so the script can use the SDK path when it supports the requested image parameters.
- Missing credentials in a non-interactive run: set environment variables or run `python skills/ranger-image-2/scripts/generate_image.py --configure` in a terminal.
- `openai SDK is not installed`: the script falls back to raw HTTP; if your provider requires SDK-specific transport behavior, run `python -m pip install openai` in the active environment.
- Existing output path: pass `--force` or choose a new filename.
