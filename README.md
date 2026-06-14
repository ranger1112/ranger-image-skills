# Ranger Image Skills

English | [简体中文](README.zh-CN.md)

Reusable Codex/agent skills for Ranger-compatible image generation workflows.

## Skills

- `ranger-image-2` — Generate images with `gpt-image-2` through a configured OpenAI-compatible Image API endpoint.

## Install

From GitHub after this repository is published:

```bash
npx skills add ranger1112/ranger-image-skills --skill ranger-image-2
```

Or from a local checkout:

```bash
npx skills add . --skill ranger-image-2
```

## Configure

Set credentials in your shell environment, or run the one-time local Codex configuration flow. Do not commit secrets.

Environment variables have highest priority. For persistent local reuse, run:

```bash
python skills/ranger-image-2/scripts/generate_image.py --configure
```

The script asks for missing values, hides API-key input, and can save them under `~/.codex/ranger-image-2/config.json`.

If you have an older custom endpoint such as `https://your-provider.example/api/image/generate`, provide it as `CUSTOM_IMAGE_URL`; the skill normalizes the same origin to `/v1` and calls `/v1/images/generations`.

Use a provider-specific custom image URL only as an environment variable, not as committed configuration.

## Example

```bash
python skills/ranger-image-2/scripts/generate_image.py \
  --prompt "A golden sunset afterglow over calm water, painterly style, no text." \
  --out output/imagegen/sunset.png \
  --size 1536x1024 \
  --quality high \
  --force
```

Batch output and response debugging:

```bash
python skills/ranger-image-2/scripts/generate_image.py \
  --prompt "Three cute robot mascot sticker variations, no text." \
  --out output/imagegen/robot.png \
  --n 3 \
  --response-format b64_json \
  --save-response-json \
  --force
```

When multiple images are returned, the first image uses `--out`; additional files are saved as `name-2.ext`, `name-3.ext`, etc. If an upstream returns image URLs, use `--response-format url`; the script downloads URL outputs with a size limit.

Image edit with a local file:

```bash
python skills/ranger-image-2/scripts/generate_image.py \
  --edit \
  --image input/source.png \
  --prompt "Replace the background with a neon cyberpunk street, keep the main subject." \
  --out output/imagegen/edit.png \
  --force
```

Image edit using a provider extension that accepts remote image URLs:

```bash
python skills/ranger-image-2/scripts/generate_image.py \
  --edit \
  --image-url "https://example.com/source.png" \
  --prompt "Turn this into a watercolor illustration." \
  --out output/imagegen/edit-url.png \
  --response-format b64_json \
  --force
```

## Notes

- The script reads API keys from environment variables or the user-local Codex config file.
- The script does not print API keys.
- The script persists API keys only when `--configure` is run, under `~/.codex/ranger-image-2/config.json`.
- `--save-response-json` stores the raw Image API response next to `--out` unless you pass an explicit path.
- `--edit` supports local `--image` / `--mask` files and remote `--image-url` / `--mask-url` provider extensions. Do not mix local files and remote URLs in one edit request.
- Generated images should be treated as local outputs and are ignored by git.
