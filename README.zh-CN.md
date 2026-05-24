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
  --size 1536x1024 \
  --quality high \
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
