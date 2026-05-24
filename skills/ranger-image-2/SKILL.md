---
name: ranger-image-2
description: Generate images with gpt-image-2 through an OpenAI-compatible Image API using the current OPENAI_API_KEY, OPENAI_BASE_URL, or CUSTOM_IMAGE_URL environment variables. Use when the user asks to call gpt-image-2 via API/CLI, /v1/images/generations, the prior /api/image/generate endpoint flow, or wants the faster API route instead of Codex CLI image_generation/session extraction.
---

# Ranger Image 2

Use this skill to generate raster images through an OpenAI-compatible Image API with `gpt-image-2`.

## Rules

- Read credentials from environment only; never echo, persist, or commit API keys.
- Prefer `scripts/generate_image.py` instead of hand-writing one-off API callers.
- Use the API route for speed when the user rejects the Codex CLI `--enable image_generation` session-extraction skill as too slow.
- If `CUSTOM_IMAGE_URL` is set to a path such as `https://host/api/image/generate`, normalize the same origin to `https://host/v1` and call `/v1/images/generations`; this workspace observed `/api/image/generate` returning 404 while `/v1` routes worked.
- Keep the user's prompt verbatim unless they ask for prompt polishing.

## Quick start

```powershell
python skills/ranger-image-2/scripts/generate_image.py `
  --prompt "Create a sunset afterglow..." `
  --out output/imagegen/sunset.png `
  --size 1536x1024 `
  --quality high `
  --force
```

Set credentials and endpoint values in the shell environment before running. If `OPENAI_BASE_URL` is already set, the script uses it directly. Otherwise it derives the provider origin plus `/v1` from `CUSTOM_IMAGE_URL`.

## Workflow

1. Confirm `OPENAI_API_KEY` exists without printing it:
   ```powershell
   [bool]$env:OPENAI_API_KEY
   ```
2. Confirm one endpoint source exists:
   ```powershell
   [bool]$env:OPENAI_BASE_URL; [bool]$env:CUSTOM_IMAGE_URL
   ```
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
- TLS errors from `urllib`: use the bundled script/OpenAI SDK path instead of raw `urllib`.
- `openai SDK is not installed`: run `python -m pip install openai` in the active environment.
- Existing output path: pass `--force` or choose a new filename.
