# Clip Lab

Clip Lab is an experimental, backend-first pipeline for turning long-form video into short-form
vertical clips. It provides a Python CLI, a FastAPI service, a Remotion renderer, Docker Compose,
and a stable output contract for generated clip assets.

It is for developers, technical creators, and agencies who want a local, inspectable clip
generation workflow instead of a hosted black box. The optional web app is only a demo surface; the
main product is the backend pipeline.

## What It Solves

Long-form video repurposing usually involves several manual steps: ingesting media, transcribing,
finding moments, cutting clips, reframing to 9:16, adding captions, rendering, and packaging files
for review. Clip Lab keeps those steps in one reproducible local workflow with deterministic fixture
mode for development and tests.

## Current Status

Clip Lab is public-ready as an early open-source project, not a polished SaaS product.

Works today:

- CLI and FastAPI job creation
- local file and URL ingest
- transcript-JSON fixture mode with no model key
- optional WhisperX transcription
- deterministic local clip scoring
- optional OpenRouter-backed clip intelligence
- FFmpeg cutting and vertical reframing
- Remotion rendering
- `metadata.json`, `transcript.json`, `scenes.json`, rendered clips, and `export.zip`

Current limitations:

- job state is in memory
- no auth, accounts, billing, or hosted storage
- no social posting or scheduling
- real transcription can be slow and resource-heavy
- OpenRouter model availability and free-model limits can change outside this repo
- the web app is a demo, not the primary supported interface

## Architecture

```text
apps/
  api/        FastAPI app and CLI entrypoint
  renderer/   Remotion composition and render service
  web/        Optional demo dashboard

packages/
  pipeline/           End-to-end coordinator and output contract
  shared/             Pydantic schemas
  transcription/      Provider interface plus optional WhisperX adapter
  clip_intelligence/  Candidate mining, critic pass, packaging, model provider layer
  video_processing/   Ingest, FFmpeg, scene detection, reframe
  captions/           Remotion prop generation

fixtures/
  sample.mp4
  sample.transcript.json
```

High-level flow:

```text
video -> ingest -> audio -> transcript -> clip candidates -> critic -> packaging
      -> FFmpeg cuts -> vertical reframe -> Remotion render -> output/<job_id>/
```

More detail is in [docs/architecture.md](docs/architecture.md).

## Quickstart

```bash
git clone https://github.com/sommbc/clip-lab.git
cd clip-lab
cp .env.example .env
docker compose up --build
```

In another terminal, run the fixture pipeline without WhisperX or model calls:

```bash
docker compose exec api clip-lab /app/fixtures/sample.mp4 \
  --transcript-json /app/fixtures/sample.transcript.json \
  --output-root /app/output \
  --job-id quickstart-fixture \
  --no-render
```

Generated files appear in `output/quickstart-fixture/`.

## Docker

Default Compose services:

- `api`: FastAPI app and `clip-lab` CLI
- `renderer`: Remotion render service

Useful commands:

```bash
docker compose build
docker compose up -d --wait
docker compose ps
docker compose logs api
docker compose logs renderer
docker compose down
```

The optional demo web app is behind a profile:

```bash
docker compose --profile web up --build
```

WhisperX is intentionally excluded from the default API image. Build the heavier image only when
real transcription is needed:

```bash
INSTALL_WHISPERX=true docker compose build api
```

See [docs/docker.md](docs/docker.md).

## Local Development

Docker is the supported path for most backend work. For local Python development:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,video]"
```

Install renderer dependencies:

```bash
cd apps/renderer
npm install
cd service
npm install
```

Run the API locally:

```bash
uvicorn cliplab_api.main:app --reload --app-dir apps/api
```

Run the renderer service locally:

```bash
cd apps/renderer/service
REMOTION_BUNDLE_PATH=.. OUTPUT_DIR=../../../output npm run dev
```

## Tests And Checks

```bash
python -m pytest
python -m ruff check apps packages tests
python -m compileall apps/api packages
python -c "import cliplab_api.main; print('api import ok')"
clip-lab --help
```

Renderer and web builds:

```bash
cd apps/renderer && npm ci && npm run build
cd service && npm ci && npm run build
cd ../../web && npm ci && npm run build
```

Optional web lint:

```bash
cd apps/web && npm run lint
```

The optional web demo uses Vite 7 and requires Node `^20.19.0` or `>=22.12.0`.

## Environment Variables

Use `.env.example` as the template. Keep real keys only in local `.env`; `.env` is ignored.

Core variables:

```bash
CLIP_LAB_OUTPUT_ROOT=/app/output
CLIP_LAB_MAX_CLIPS=5
CLIP_LAB_RENDERER_URL=http://renderer:3100
CLIP_LAB_TRANSCRIPTION_PROVIDER=whisperx
CLIP_LAB_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
INSTALL_WHISPERX=false
```

OpenRouter is optional and only used when the CLI/API request enables a model provider:

```bash
CLIP_LAB_MODEL_PROVIDER=openrouter
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
CLIP_LAB_CANDIDATE_MODEL=
CLIP_LAB_CRITIC_MODEL=
CLIP_LAB_PACKAGING_MODEL=
```

WhisperX variables:

```bash
CLIP_LAB_WHISPERX_MODEL=large-v3
CLIP_LAB_WHISPERX_DEVICE=cpu
CLIP_LAB_WHISPERX_COMPUTE_TYPE=int8
CLIP_LAB_WHISPERX_BATCH_SIZE=16
CLIP_LAB_WHISPERX_ALIGN=true
HUGGINGFACE_TOKEN=
```

## Example Workflow

1. Start the backend stack:

```bash
docker compose up -d --build --wait
```

2. Run fixture mode:

```bash
docker compose exec api clip-lab /app/fixtures/sample.mp4 \
  --transcript-json /app/fixtures/sample.transcript.json \
  --output-root /app/output \
  --job-id demo-fixture
```

3. Inspect:

```text
output/demo-fixture/
  clips/raw/
  clips/vertical/
  clips/rendered/
  render_props/
  metadata.json
  transcript.json
  scenes.json
  export.zip
```

## Roadmap

- keep fixture and Docker smoke tests reliable
- add a small real-transcription regression fixture
- improve crop quality and speaker-aware framing
- add sidecar captions such as SRT/VTT
- add persistent job storage before any hosted deployment
- keep social posting, auth, teams, billing, and scheduling out of scope until the core pipeline is stronger

## Documentation

- [Quickstart](docs/quickstart.md)
- [Docker](docs/docker.md)
- [API](docs/api.md)
- [CLI](docs/cli.md)
- [Architecture](docs/architecture.md)
- [Pipeline](docs/pipeline.md)
- [Output contract](docs/output-contract.md)
- [Model providers](docs/model-providers.md)
- [Secrets](docs/secrets.md)
- [Troubleshooting](docs/troubleshooting.md)

## License

MIT. See [LICENSE](LICENSE).
