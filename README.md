# Ranger Image Skills

Reusable Codex/agent skills for Ranger-compatible image generation workflows.

## Skills

- `ranger-image-2` — Generate images with `gpt-image-2` through a configured OpenAI-compatible Image API endpoint.

## Install

From GitHub after this repository is published:

```bash
npx skills add QLHazyCoder/ranger-image-skills --skill ranger-image-2
```

Or from a local checkout:

```bash
npx skills add . --skill ranger-image-2
```

## Configure

Set credentials in your shell environment. Do not commit secrets.

Set `OPENAI_API_KEY` and either `OPENAI_BASE_URL` or `CUSTOM_IMAGE_URL` in your shell environment. Keep the values out of files and command transcripts.

If you have an older custom endpoint such as `https://your-provider.example/api/image/generate`, set it as `CUSTOM_IMAGE_URL`; the skill normalizes the same origin to `/v1` and calls `/v1/images/generations`.

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

## Notes

- The script reads API keys only from environment variables.
- The script does not print or persist API keys.
- Generated images should be treated as local outputs and are ignored by git.
