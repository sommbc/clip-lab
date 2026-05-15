from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cliplab_pipeline import ClipLabPipeline, PipelineConfig
from cliplab_transcription import load_normalized_transcript_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Clip Lab clip generation pipeline.")
    parser.add_argument("source", help="YouTube/video URL or local video path.")
    parser.add_argument(
        "--output-root",
        default=os.environ.get("CLIP_LAB_OUTPUT_ROOT", "output"),
        help="Output directory root.",
    )
    parser.add_argument("--job-id", default=None, help="Optional stable job id.")
    parser.add_argument(
        "--max-clips",
        type=int,
        default=int(os.environ.get("CLIP_LAB_MAX_CLIPS", "5")),
    )
    parser.add_argument("--no-render", action="store_true", help="Skip Remotion render service.")
    parser.add_argument(
        "--renderer-url",
        default=os.environ.get("CLIP_LAB_RENDERER_URL", "http://localhost:3100"),
    )
    parser.add_argument(
        "--transcript-json",
        default=None,
        help="Use an existing normalized transcript JSON instead of running WhisperX.",
    )
    parser.add_argument(
        "--use-model-provider",
        action="store_true",
        help="Use CLIP_LAB_MODEL_PROVIDER or --model-provider for model-backed intelligence.",
    )
    parser.add_argument(
        "--model-provider",
        default=None,
        help="Model provider to use when --use-model-provider is set: fake, dev, or openrouter.",
    )
    parser.add_argument("--no-zip", action="store_true", help="Skip export.zip creation.")
    args = parser.parse_args()

    try:
        transcript = None
        if args.transcript_json:
            transcript = load_normalized_transcript_json(args.transcript_json)

        pipeline = ClipLabPipeline(
            config=PipelineConfig(
                output_root=Path(args.output_root),
                max_clips=args.max_clips,
                render=not args.no_render,
                renderer_url=args.renderer_url,
                use_model_provider=args.use_model_provider,
                model_provider_name=args.model_provider,
                write_zip=not args.no_zip,
            )
        )
        metadata = pipeline.run(source=args.source, job_id=args.job_id, transcript=transcript)
        print(metadata.model_dump_json(indent=2, exclude_none=True))
    except Exception as exc:
        print(f"Clip Lab error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
