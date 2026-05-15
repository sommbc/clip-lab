# Docker

Docker is the primary developer path for Clip Lab backend work.

## Install

On macOS, install Docker Desktop and make sure the engine is running:

```bash
docker --version
docker compose version
docker run hello-world
```

You may need to sign in to Docker Desktop manually for Docker Hub features, but the fixture flow
does not require product auth, billing, or any Clip Lab account.

## Start The Backend Stack

```bash
cp .env.example .env
docker compose up --build
```

For CI-style startup:

```bash
docker compose build
docker compose up -d --wait
```

Default services:

- `api`: FastAPI app and `clip-lab` CLI
- `renderer`: Remotion render service

Default host mounts:

- `./output` to `/app/output` in the API container
- `./output` to `/output` in the renderer container
- `./uploads` to `/app/uploads`
- `./fixtures` to `/app/fixtures` read-only

The optional demo web app is behind a Compose profile:

```bash
docker compose --profile web up --build
```

## Verify Without WhisperX

```bash
docker compose exec api clip-lab ./fixtures/sample.mp4 \
  --transcript-json ./fixtures/sample.transcript.json \
  --output-root output \
  --no-render
```

This exercises ingest, audio extraction, clip selection, FFmpeg cutting, vertical reframe,
Remotion prop generation, output metadata, and ZIP export. It does not download WhisperX or call a
model provider.

## Verify Full Render

```bash
docker compose exec api clip-lab ./fixtures/sample.mp4 \
  --transcript-json ./fixtures/sample.transcript.json \
  --output-root output
```

The API calls `http://renderer:3100`, and both containers write to the shared output mount.

## Optional WhisperX

WhisperX is not installed in the default API image. Build the heavier image only when real
transcription is needed:

```bash
INSTALL_WHISPERX=true docker compose build api
docker compose up
```

Set WhisperX options in `.env`:

```bash
CLIP_LAB_WHISPERX_MODEL=large-v3
CLIP_LAB_WHISPERX_DEVICE=cpu
CLIP_LAB_WHISPERX_COMPUTE_TYPE=int8
CLIP_LAB_WHISPERX_BATCH_SIZE=16
CLIP_LAB_WHISPERX_ALIGN=true
HUGGINGFACE_TOKEN=
```

## Optional OpenRouter

Model-backed intelligence is opt-in. Fixture runs do not need keys.

```bash
CLIP_LAB_MODEL_PROVIDER=openrouter
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
CLIP_LAB_CANDIDATE_MODEL=
CLIP_LAB_CRITIC_MODEL=
CLIP_LAB_PACKAGING_MODEL=
```

Then pass `--use-model-provider` to the CLI or `use_model_provider=true` to the API.

## Useful Commands

```bash
docker compose ps
docker compose logs api
docker compose logs renderer
docker compose down
docker compose down --volumes
```
