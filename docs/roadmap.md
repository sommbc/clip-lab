# Roadmap

This roadmap is intentionally practical. Clip Lab should stay focused on clip generation before
adding distribution features.

## Near-Term Verification

- Keep the fixture-based local media smoke path green for every pipeline change.
- Real WhisperX end-to-end test with a short known fixture and word-level timestamp assertions.
- Real YouTube ingest test using `yt-dlp` against a stable public fixture or recorded HTTP fixture.
- Docker Compose verification once `docker compose` is available in the local/dev environment.

## Clip Quality

- Caption style presets for creator, podcast, documentary, product, and educational clips.
- Crop quality improvements, including first-party speaker-aware tracking in
  `packages/video_processing`.
- Better scene-aware boundary scoring so cuts prefer sentence, silence, and shot-change alignment.
- More explicit risk flags for sponsor reads, sensitive claims, missing context, and unsupported
  platform fit.

## Export Workflow

- Downloadable ZIP export containing MP4 clips, transcript JSON, metadata JSON, and captions.
- Stable metadata manifest for downstream automations and agency handoff.
- Optional SRT/VTT sidecar export in addition to burned-in captions.

## Later, Not Now

- Social posting and scheduling.
- Account/team workflows.
- Hosted job persistence and billing.
