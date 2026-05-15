# CLI

The CLI entrypoint is `clip-lab`.

## Help

```bash
clip-lab --help
```

Inside Docker:

```bash
docker compose exec api clip-lab --help
```

## No-Render Fixture Run

```bash
docker compose exec api clip-lab ./fixtures/sample.mp4 \
  --transcript-json ./fixtures/sample.transcript.json \
  --output-root output \
  --no-render
```

This path is the fastest backend verification path and does not require WhisperX.

## Full Render Fixture Run

```bash
docker compose exec api clip-lab ./fixtures/sample.mp4 \
  --transcript-json ./fixtures/sample.transcript.json \
  --output-root output
```

The API container calls the renderer service at `CLIP_LAB_RENDERER_URL`.

## Options

```text
source
  YouTube/video URL or local video path.

--output-root
  Output root. Docker defaults to /app/output. The documented Docker command uses output.

--job-id
  Optional stable job id for repeatable output paths.

--max-clips
  Maximum accepted clips.

--no-render
  Skip Remotion rendering and stop after vertical clips plus render props.

--renderer-url
  Renderer service URL. Docker defaults to http://renderer:3100.

--transcript-json
  Existing normalized transcript JSON. Use this for fixture verification and offline tests.

--use-model-provider
  Opt into model-backed clip intelligence. Fixture mode does not need this.

--model-provider
  Provider used when --use-model-provider is set. Supported: fake, dev, openrouter.

--no-zip
  Skip export.zip creation.
```

## Environment

```bash
CLIP_LAB_OUTPUT_ROOT=/app/output
CLIP_LAB_MAX_CLIPS=5
CLIP_LAB_RENDERER_URL=http://renderer:3100
CLIP_LAB_TRANSCRIPTION_PROVIDER=whisperx
CLIP_LAB_MODEL_PROVIDER=openrouter
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
CLIP_LAB_CANDIDATE_MODEL=
CLIP_LAB_CRITIC_MODEL=
CLIP_LAB_PACKAGING_MODEL=
```

## YouTube URL Input

```bash
clip-lab "https://www.youtube.com/watch?v=VIDEO_ID" --no-render
```

URL input uses `yt-dlp`. Some videos require local cookies; cookie files must never be committed.

## ZIP Export

By default the CLI writes `output/<job_id>/export.zip` alongside metadata and clip files.
