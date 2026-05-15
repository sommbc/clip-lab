# Troubleshooting

## Docker Compose Does Not Become Healthy

Check services:

```bash
docker compose ps
docker compose logs api
docker compose logs renderer
```

The API health endpoint is:

```bash
curl http://localhost:8000/health
```

The renderer health endpoint is:

```bash
curl http://localhost:3100/health
```

## Fixture Run Fails With WhisperX Error

Use `--transcript-json` for fixture mode:

```bash
docker compose exec api clip-lab ./fixtures/sample.mp4 \
  --transcript-json ./fixtures/sample.transcript.json \
  --output-root output \
  --no-render
```

Without a transcript JSON, the pipeline attempts real transcription.

## Renderer Unavailable

Run with `--no-render` for backend-only verification or start the renderer service:

```bash
docker compose up --build
```

## Missing OpenRouter Key

Model keys are only needed when `--use-model-provider` or the API `use_model_provider=true` field
is used. Fixture mode without model-provider usage requires no key.

## YouTube Download Fails

YouTube availability changes and some videos require cookies. Cookie files are local-only and must
not be committed. Use a local file input when debugging unrelated pipeline behavior.

## FFmpeg Missing

Install FFmpeg locally or use Docker. The Docker API and renderer images include FFmpeg.
