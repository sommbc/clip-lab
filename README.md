# Clip Lab

[![CI](https://github.com/sommbc/clip-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/sommbc/clip-lab/actions/workflows/ci.yml)

Local-first pipeline for turning long-form video into short-form vertical clips.

Clip Lab is an experimental, backend-first project for developers who want an inspectable clip
generation workflow: ingest media, use a transcript, select candidate moments, cut clips, reframe
to 9:16, generate render props, optionally render with Remotion, and package the result.

It is not a hosted SaaS, social scheduler, or account system. The supported surface is the Python
CLI, FastAPI service, Docker Compose stack, Remotion render service, and documented output contract.

## Why It Exists

Repurposing long-form video usually turns into a pile of manual steps and one-off scripts. Clip Lab
keeps the core workflow in a reproducible local pipeline so technical teams can inspect the
intermediate artifacts, test deterministic fixture runs, and swap in heavier transcription or model
providers only when needed.

## What Works Today

- Python CLI and FastAPI job creation
- local file and URL ingest
- transcript-JSON fixture mode with no model key
- optional WhisperX transcription
- deterministic local clip scoring
- optional OpenRouter-backed clip intelligence
- FFmpeg cutting and 1080x1920 vertical reframing
- Remotion render service
- `metadata.json`, `transcript.json`, `scenes.json`, clip files, render props, and `export.zip`

## Current Limits

- early open-source project, not a polished product
- job state is in memory
- no auth, users, billing, hosted storage, posting, or scheduling
- real transcription can be slow and resource-heavy
- model-backed intelligence depends on external provider availability and rate limits
- browser UI is optional and secondary to the backend workflow

## Public Review Status

Clip Lab is intentionally public as a local-first developer pipeline. It has a fixture path that runs without private media, WhisperX, or model keys; CI checks backend tests, renderer builds, optional web build, Docker Compose smoke, dependency audits, public-tree hygiene, and secret patterns. See [Public Review Notes](docs/public-review.md).

## Quickstart

```bash
git clone https://github.com/sommbc/clip-lab.git
cd clip-lab
cp .env.example .env
docker compose up -d --build --wait
```

Run the fixture pipeline without WhisperX or model calls:

```bash
docker compose exec -T api clip-lab /app/fixtures/sample.mp4 \
  --transcript-json /app/fixtures/sample.transcript.json \
  --output-root /app/output \
  --job-id quickstart-fixture \
  --no-render
```

Inspect the result:

```bash
find output/quickstart-fixture -maxdepth 3 -type f | sort
```

Clean up:

```bash
docker compose down
```

## Successful Example

A successful fixture run creates this shape:

```text
output/quickstart-fixture/
  audio/source.wav
  clips/raw/clip_01.mp4
  clips/vertical/clip_01.mp4
  metadata.json
  render_props/clip_01.json
  scenes.json
  source/sample.mp4
  transcript.json
  export.zip
```

When rendering is enabled, final MP4s are also written under `clips/rendered/`.

## Architecture

```text
apps/
  api/        FastAPI app and CLI entrypoint
  renderer/   Remotion composition and render service
  web/        Optional browser UI

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
      -> FFmpeg cuts -> vertical reframe -> Remotion props/render -> output/<job_id>/
```

More detail: [docs/architecture.md](docs/architecture.md).

## Commands

| Task | Command |
| --- | --- |
| Start Docker stack | `docker compose up -d --build --wait` |
| Fixture no-render run | `docker compose exec -T api clip-lab /app/fixtures/sample.mp4 --transcript-json /app/fixtures/sample.transcript.json --output-root /app/output --job-id quickstart-fixture --no-render` |
| Full fixture render | `docker compose exec -T api clip-lab /app/fixtures/sample.mp4 --transcript-json /app/fixtures/sample.transcript.json --output-root /app/output --job-id quickstart-render` |
| Python tests | `python -m pytest` |
| Python lint | `python -m ruff check apps packages tests` |
| Python compile | `python -m compileall apps/api packages` |
| Renderer build | `cd apps/renderer && npm ci && npm run build` |
| Renderer service build | `cd apps/renderer/service && npm ci && npm run build` |
| Browser UI build | `cd apps/web && npm ci && npm run lint && npm run build` |
| Stop Docker stack | `docker compose down` |

## Local Development

Docker is the supported path for most backend work. For local Python development:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,video]"
```

Run local checks:

```bash
python -m pytest
python -m ruff check apps packages tests
python -m compileall apps/api packages
python -c "import cliplab_api.main; print('api import ok')"
clip-lab --help
```

Install renderer dependencies:

```bash
cd apps/renderer
npm ci
cd service
npm ci
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

## Environment

Use `.env.example` as the template. Real keys belong only in local `.env`; `.env` is ignored.

Core variables:

```bash
CLIP_LAB_OUTPUT_ROOT=/app/output
CLIP_LAB_MAX_CLIPS=5
CLIP_LAB_RENDERER_URL=http://renderer:3100
CLIP_LAB_TRANSCRIPTION_PROVIDER=whisperx
CLIP_LAB_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
INSTALL_WHISPERX=false
```

OpenRouter is optional and only used when `--use-model-provider` or the matching API field is set:

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

## Security And Privacy

Clip Lab is designed for local processing. The default fixture workflow requires no model key,
account, cookies, private media, or hosted service.

- Do not commit `.env`, API keys, cookies, uploads, generated clips, or model weights.
- Uploaded API files are written under `uploads/`; generated jobs are written under `output/`.
- CLI and API job IDs are constrained to safe path characters before writing output.
- OpenRouter requests are opt-in and send prompt/transcript content to the configured provider.
- WhisperX can require model downloads and optional Hugging Face credentials.

See [SECURITY.md](SECURITY.md) and [docs/secrets.md](docs/secrets.md).

## Licensing And Attribution

Project code is MIT licensed. Clip Lab does not vendor third-party application source trees, model
weights, private media, or generated outputs. The bundled Noto Serif font used by the renderer is
covered by the SIL Open Font License; see [NOTICE.md](NOTICE.md) and
[LICENSES/OFL-1.1.txt](LICENSES/OFL-1.1.txt).

Runtime dependencies such as FFmpeg, Remotion, WhisperX, OpenCV, and yt-dlp are installed as
packages or system tools. Their own licenses apply when users install or build the stack.

## Roadmap

- keep fixture and Docker smoke tests reliable
- add a small real-transcription regression fixture
- improve crop quality and speaker-aware framing
- add sidecar captions such as SRT/VTT
- add persistent job storage before any hosted deployment
- keep auth, billing, social posting, teams, and scheduling out of scope until the core pipeline is stronger

## Contributing

Start with [CONTRIBUTING.md](CONTRIBUTING.md). Keep changes backend-first, fixture-verifiable, and
inside the documented output contract. Do not add private media, credentials, account systems, or
generated artifacts.

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
- [Licensing](docs/licensing.md)
- [Examples](examples/README.md)

## License

MIT. See [LICENSE](LICENSE).
