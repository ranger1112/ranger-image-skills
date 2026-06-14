# Ranger Image Skills

[English](README.md) | 简体中文

可复用的 Codex / Agent Skills，用于 Ranger 兼容的图片生成工作流。

## Skills

- `ranger-image-2`：通过 OpenAI-compatible Image API endpoint 调用 `gpt-image-2` 生成图片。

## 安装

从 GitHub 安装：

```bash
npx skills add ranger1112/ranger-image-skills --skill ranger-image-2
```

或者从本地 checkout 安装：

```bash
npx skills add . --skill ranger-image-2
```

## 配置

可以在 shell 环境变量中配置凭据和 endpoint，也可以运行一次本地 Codex 配置流程。不要把密钥提交到仓库。

环境变量优先级最高。若想持久化到本机复用，运行：

```bash
python skills/ranger-image-2/scripts/generate_image.py --configure
```

脚本会询问缺失值，API key 输入会隐藏，并可在确认后保存到 `~/.codex/ranger-image-2/config.json`。

至少需要：

- `OPENAI_API_KEY`：API key。
- `OPENAI_BASE_URL`：OpenAI-compatible base URL，例如 provider 的 `/v1` 地址。

如果你只有旧格式的自定义 endpoint，例如 `https://your-provider.example/api/image/generate`，可以作为 `CUSTOM_IMAGE_URL` 提供。Skill 会自动把同源地址归一到 `/v1`，并调用 `/v1/images/generations`。

## 示例

```bash
python skills/ranger-image-2/scripts/generate_image.py \
  --prompt "A golden sunset afterglow over calm water, painterly style, no text." \
  --out output/imagegen/sunset.png \
  --preset landscape \
  --quality high \
  --force
```

内置 preset：`square`（`1024x1024`）、`landscape`（`1536x1024`）、`portrait`（`1024x1536`）、`4k-landscape`（`3840x2160`）、`4k-portrait`（`2160x3840`）。也可以继续用 `--size WIDTHxHEIGHT` 传自定义尺寸；`--preset` 与 `--size` 互斥。4K preset 会原样传给 provider，是否真正支持取决于上游模型和 endpoint。

批量输出和响应调试：

```bash
python skills/ranger-image-2/scripts/generate_image.py \
  --prompt "Three cute robot mascot sticker variations, no text." \
  --out output/imagegen/robot.png \
  --n 3 \
  --response-format b64_json \
  --save-response-json \
  --force
```

如果返回多张图片，第一张写入 `--out`，后续自动写成 `name-2.ext`、`name-3.ext`。如果上游支持 URL 响应，可以使用 `--response-format url`；脚本会下载 URL 输出，并受 `--max-download-bytes` 限制。若只想保存返回的 URL、不下载图片，添加 `--no-download-url`，脚本会写入 `*.url.txt` sidecar 文件。

本地文件图像编辑：

```bash
python skills/ranger-image-2/scripts/generate_image.py \
  --edit \
  --image input/source.png \
  --prompt "Replace the background with a neon cyberpunk street, keep the main subject." \
  --out output/imagegen/edit.png \
  --force
```

使用支持远程图片 URL 的 provider 扩展做图像编辑：

```bash
python skills/ranger-image-2/scripts/generate_image.py \
  --edit \
  --image-url "https://example.com/source.png" \
  --prompt "Turn this into a watercolor illustration." \
  --out output/imagegen/edit-url.png \
  --response-format b64_json \
  --force
```

只保留 provider 返回 URL、不下载图片：

```bash
python skills/ranger-image-2/scripts/generate_image.py \
  --prompt "A cinematic mountain panorama, no text." \
  --out output/imagegen/mountain.png \
  --response-format url \
  --no-download-url \
  --force
```

长 prompt 建议放到文件里，避免 shell 引号转义问题：

```bash
python skills/ranger-image-2/scripts/generate_image.py \
  --prompt-file prompt.txt \
  --out output/imagegen/result.png \
  --force
```

## 行为说明

- 默认模型：`gpt-image-2`。
- 默认尺寸：`1536x1024`。
- 默认质量：`high`。
- 默认输出格式：`png`。
- 支持 `--preset square|landscape|portrait|4k-landscape|4k-portrait`，4K 是否成功由 provider 能力决定。
- 支持 `--size WIDTHxHEIGHT` 正整数尺寸校验；`--size` 与 `--preset` 不能同时使用。
- 支持 `--n` 批量请求，并自动拆分保存多张图片。
- 支持 `--response-format b64_json|url`；URL 输出会下载为本地文件。
- 支持 `--no-download-url`：URL 输出不下载，改写为 `*.url.txt` sidecar 文件。
- 支持 `--save-response-json` 保存原始 Image API 响应，便于排查 provider 差异。
- 支持 `--edit` 图像编辑：本地文件用 `--image` / `--mask`，远程 URL provider 扩展用 `--image-url` / `--mask-url`。同一次编辑请求不要混用本地文件和远程 URL。
- 脚本从环境变量或用户本地 Codex 配置文件读取 API key。
- 脚本不会打印 API key。
- 脚本只会在交互确认后把 API key 保存到 `~/.codex/ranger-image-2/config.json`。
- 生成图片属于本地输出，已通过 `.gitignore` 忽略。

## 排障

- 如果 `/api/image/generate` 返回 `404 page not found`：改用同一 host 的 `/v1/images/generations`；脚本会自动做这个归一化。
- 如果非交互环境缺少凭据：设置环境变量，或在终端运行 `python skills/ranger-image-2/scripts/generate_image.py --configure`。
- 如果缺少 OpenAI SDK：运行 `python -m pip install openai`。
- 如果输出文件已存在：添加 `--force`，或者换一个输出文件名。

## 许可证

MIT
