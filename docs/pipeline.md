# Pipeline

Clip Lab turns a local file or URL into vertical clips through a fixed backend pipeline.

## Stages

1. Ingest local file or YouTube/video URL.
2. Extract mono 16 kHz WAV audio.
3. Load a transcript fixture or run the configured transcription provider.
4. Normalize transcript output into `NormalizedTranscript`.
5. Detect scenes.
6. Mine clip candidates.
7. Refine boundaries using word timestamps.
8. Run critic/editor rejection.
9. Package clip metadata.
10. Cut raw source-aspect clips.
11. Reframe clips to 1080x1920 vertical MP4.
12. Write Remotion render props.
13. Optionally render final clips through the renderer service.
14. Write metadata, transcript, scenes, and `export.zip`.

## Package Ownership

- `packages/pipeline`: end-to-end pipeline coordinator
- `packages/transcription`: provider interface and WhisperX adapter
- `packages/clip_intelligence`: candidate, critic, packaging, provider layer, prompt versions
- `packages/video_processing`: ingest, FFmpeg, FFprobe, scene detection, reframe
- `packages/captions`: Remotion prop creation
- `packages/shared`: Pydantic schemas

`apps/api` only exposes HTTP and CLI entrypoints.

## Modes

Fixture no-render:

- no WhisperX
- no API keys
- no renderer request

Fixture full-render:

- no WhisperX
- no API keys
- renderer required

Real transcription:

- WhisperX optional dependency required
- Hugging Face token only required for diarization/private model paths

Model-backed intelligence:

- opt-in through CLI/API flags
- OpenRouter key and model vars required only when used
