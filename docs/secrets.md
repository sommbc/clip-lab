# Secrets

Clip Lab must be safe to publish and clone.

## Allowed In Git

- `.env.example` with empty placeholders
- deterministic fixtures under `fixtures/`
- public documentation
- provider names and base URLs

## Never Commit

- `.env`
- `.env.*`
- `OPENROUTER_API_KEY`
- `HUGGINGFACE_TOKEN`
- YouTube cookies
- private prompts
- private local paths
- raw uploads
- downloaded media
- generated clips
- model weights and caches

## Local Secret Setup

Copy the example file:

```bash
cp .env.example .env
```

Put real values only in `.env`:

```bash
OPENROUTER_API_KEY=
CLIP_LAB_CANDIDATE_MODEL=
CLIP_LAB_CRITIC_MODEL=
CLIP_LAB_PACKAGING_MODEL=
HUGGINGFACE_TOKEN=
```

Fixture mode does not need those values. OpenRouter keys are only required when the CLI or API is
run with model-provider usage enabled.

## YouTube Cookies

Clip Lab can pass a local cookie file to `yt-dlp` through `CLIP_LAB_YOUTUBE_COOKIES`, but cookie
files must stay outside git. Do not put cookie paths in committed docs, fixtures, or scripts.

## Audit Command

Use a targeted local scan before publishing:

```bash
rg -n --hidden --glob '!node_modules/**' --glob '!output/**' \
  'sk-[A-Za-z0-9]{20,}|Bearer [A-Za-z0-9]|cookie|PRIVATE_LOCAL_PATH'
```
