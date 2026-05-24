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

在 shell 环境变量中配置凭据和 endpoint。不要把密钥提交到仓库。

至少需要：

- `OPENAI_API_KEY`：API key。
- `OPENAI_BASE_URL`：OpenAI-compatible base URL，例如 provider 的 `/v1` 地址。

如果你只有旧格式的自定义 endpoint，例如 `https://your-provider.example/api/image/generate`，可以设置为 `CUSTOM_IMAGE_URL`。Skill 会自动把同源地址归一到 `/v1`，并调用 `/v1/images/generations`。

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
- 脚本只从环境变量读取 API key。
- 脚本不会打印或持久化 API key。
- 生成图片属于本地输出，已通过 `.gitignore` 忽略。

## 排障

- 如果 `/api/image/generate` 返回 `404 page not found`：改用同一 host 的 `/v1/images/generations`；脚本会自动做这个归一化。
- 如果缺少 OpenAI SDK：运行 `python -m pip install openai`。
- 如果输出文件已存在：添加 `--force`，或者换一个输出文件名。

## 许可证

MIT
