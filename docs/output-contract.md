# Output Contract

Clip Lab writes every job under:

```text
output/<job_id>/
```

Required structure:

```text
output/<job_id>/
  source/
  audio/
  clips/raw/
  clips/vertical/
  clips/rendered/
  render_props/
  metadata.json
  transcript.json
  scenes.json
  export.zip
```

## Directories

`source/` contains the ingested input media.

`audio/` contains extracted audio, currently `source.wav`.

`clips/raw/` contains source-aspect clip cuts.

`clips/vertical/` contains 1080x1920 H.264/AAC vertical clips.

`clips/rendered/` contains final Remotion-rendered clips when rendering is enabled. It is present
even when `--no-render` is used.

`render_props/` contains one JSON prop file per clip for the renderer service.

## Files

`metadata.json` is the primary machine-readable export record. Clip paths are relative to
`output/<job_id>` where possible.

`transcript.json` is the normalized transcript used for the job.

`scenes.json` is the scene detection output.

`export.zip` is a portable archive of the job directory, excluding the ZIP file itself.

## Clip Metadata

Each clip includes:

- `id`
- `title`
- `start`
- `end`
- `duration`
- `viral_score`
- `hook_text`
- `hook_sentence`
- `viral_reason`
- `dominant_mechanism`
- `platform_fit`
- `suggested_caption`
- `risk_flags`
- `source_clip_path`
- `vertical_clip_path`
- `render_props_path`
- `rendered_clip_path` when rendering is enabled

Top-level metadata includes:

- `source`
- `source_video_path`
- `transcript_path`
- `scenes_path`
- `zip_export_path`
- `output_dir`
- `status`
- `errors`

## Stability Rule

Downstream tools should depend on this directory shape and relative path contract, not on temporary
container paths such as `/app/output` or `/output`.
