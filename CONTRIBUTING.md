# Contributing

Clip Lab is backend-first. The core contribution surface is the pipeline, CLI, API, renderer
service, output contract, tests, and Docker workflow.

## Local Setup

```bash
cp .env.example .env
docker compose up --build
```

Run the fixture path without external keys:

```bash
docker compose exec api clip-lab ./fixtures/sample.mp4 \
  --transcript-json ./fixtures/sample.transcript.json \
  --output-root output \
  --no-render
```

## Development Checks

```bash
python3 -m pytest
python3 -m ruff check apps packages tests
python3 -m compileall apps/api packages
python3 -c "import cliplab_api.main; print('api import ok')"
clip-lab --help
```

Renderer checks:

```bash
cd apps/renderer && npm ci && npm run build
cd service && npm ci && npm run build
```

Optional web demo:

```bash
cd apps/web && npm ci && npm run build
```

## Scope Rules

- Keep `apps/api` as orchestration only.
- Put reusable business logic in `packages/*`.
- Keep raw WhisperX data inside `packages/transcription`.
- Keep raw model-provider responses inside `packages/clip_intelligence`.
- Do not add auth, billing, social posting, private prompts, real media, cookies, or API keys.
- Keep fixture mode runnable without network, WhisperX, or model keys.

## Pull Requests

Every PR should describe the pipeline surface changed, tests run, Docker impact, and whether the
output contract changed. Include sample output paths when relevant.
