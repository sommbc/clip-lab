# API

The API is a FastAPI service exposed on port `8000` in Docker.

## Health

```bash
curl http://localhost:8000/health
```

Response:

```json
{"ok": true}
```

## Create Job

Upload a local video:

```bash
curl -F "file=@./fixtures/sample.mp4" \
  -F "render=true" \
  -F "max_clips=5" \
  http://localhost:8000/api/jobs
```

Submit a URL:

```bash
curl -F "url=https://example.com/video.mp4" \
  -F "render=true" \
  http://localhost:8000/api/jobs
```

Run fixture mode without WhisperX by providing a transcript path mounted in Docker:

```bash
curl -F "file=@./fixtures/sample.mp4" \
  -F "transcript_json_path=/app/fixtures/sample.transcript.json" \
  -F "render=false" \
  http://localhost:8000/api/jobs
```

Or upload a transcript JSON:

```bash
curl -F "file=@./fixtures/sample.mp4" \
  -F "transcript_json=@./fixtures/sample.transcript.json" \
  -F "render=false" \
  http://localhost:8000/api/jobs
```

Opt into model-backed intelligence only when keys are configured:

```bash
curl -F "file=@./fixtures/sample.mp4" \
  -F "transcript_json=@./fixtures/sample.transcript.json" \
  -F "use_model_provider=true" \
  -F "model_provider=fake" \
  -F "render=false" \
  http://localhost:8000/api/jobs
```

Response:

```json
{
  "job_id": "uuid",
  "status": "queued"
}
```

## Check Job

```bash
curl http://localhost:8000/api/jobs/<job_id>
```

The in-memory job response includes status, source, result metadata when completed, and error text
when failed.

## Files

Generated files are served from the API under:

```text
/clips/<job_id>/...
```

The canonical files on disk are under:

```text
output/<job_id>/
```

ZIP export:

```bash
curl -OJ http://localhost:8000/api/jobs/<job_id>/export.zip
```

The API job route runs real transcription when no transcript is provided. For Docker fixture
verification, pass `transcript_json` or `transcript_json_path` so WhisperX is not required.
