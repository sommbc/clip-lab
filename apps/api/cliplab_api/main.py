from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cliplab_pipeline import ClipLabPipeline, PipelineConfig
from cliplab_transcription import load_normalized_transcript_json

OUTPUT_ROOT = Path(os.environ.get("CLIP_LAB_OUTPUT_ROOT", "output"))
UPLOAD_ROOT = Path("uploads")
RENDERER_URL = os.environ.get("CLIP_LAB_RENDERER_URL", "http://localhost:3100")
DEFAULT_MAX_CLIPS = int(os.environ.get("CLIP_LAB_MAX_CLIPS", "5"))
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def _parse_cors_origins() -> list[str]:
    raw = os.environ.get("CLIP_LAB_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or DEFAULT_CORS_ORIGINS.split(",")


OUTPUT_ROOT.mkdir(exist_ok=True)
UPLOAD_ROOT.mkdir(exist_ok=True)

app = FastAPI(title="Clip Lab API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/clips", StaticFiles(directory=OUTPUT_ROOT), name="clips")

jobs: dict[str, dict[str, Any]] = {}


class JobCreateResponse(BaseModel):
    job_id: str
    status: str


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/api/jobs", response_model=JobCreateResponse)
async def create_job(
    background_tasks: BackgroundTasks,
    url: str | None = Form(None),
    file: UploadFile | None = File(None),
    transcript_json: UploadFile | None = File(None),
    transcript_json_path: str | None = Form(None),
    render: bool = Form(True),
    max_clips: int = Form(DEFAULT_MAX_CLIPS),
    use_model_provider: bool = Form(False),
    model_provider: str | None = Form(None),
) -> JobCreateResponse:
    if not url and not file:
        raise HTTPException(status_code=400, detail="Provide a URL or upload a video file.")
    if transcript_json is not None and transcript_json_path:
        raise HTTPException(
            status_code=400,
            detail="Provide transcript_json upload or transcript_json_path, not both.",
        )

    job_id = str(uuid.uuid4())
    source = url
    if file is not None:
        safe_name = Path(file.filename or "upload.mp4").name
        upload_path = UPLOAD_ROOT / f"{job_id}_{safe_name}"
        with upload_path.open("wb") as destination:
            shutil.copyfileobj(file.file, destination)
        source = str(upload_path)

    transcript_path = None
    if transcript_json is not None:
        transcript_name = Path(transcript_json.filename or "transcript.json").name
        transcript_path_obj = UPLOAD_ROOT / f"{job_id}_{transcript_name}"
        with transcript_path_obj.open("wb") as destination:
            shutil.copyfileobj(transcript_json.file, destination)
        transcript_path = str(transcript_path_obj)
    elif transcript_json_path:
        transcript_path = str(_resolve_allowed_transcript_path(transcript_json_path))

    assert source is not None
    jobs[job_id] = {
        "status": "queued",
        "source": source,
        "transcript_json_path": transcript_path,
        "result": None,
        "error": None,
    }
    background_tasks.add_task(
        run_job,
        job_id,
        source,
        render,
        max_clips,
        transcript_path,
        use_model_provider,
        model_provider,
    )
    return JobCreateResponse(job_id=job_id, status="queued")


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.get("/api/jobs/{job_id}/export.zip")
def export_job(job_id: str) -> FileResponse:
    zip_path = _resolve_job_output_dir(job_id) / "export.zip"
    if not zip_path.is_file():
        raise HTTPException(status_code=404, detail="Export ZIP not found for job.")
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"clip-lab-{job_id}.zip",
    )


def run_job(
    job_id: str,
    source: str,
    render: bool,
    max_clips: int,
    transcript_json_path: str | None,
    use_model_provider: bool,
    model_provider: str | None,
) -> None:
    jobs[job_id]["status"] = "processing"
    try:
        transcript = (
            load_normalized_transcript_json(transcript_json_path) if transcript_json_path else None
        )
        pipeline = ClipLabPipeline(
            config=PipelineConfig(
                output_root=OUTPUT_ROOT,
                max_clips=max_clips,
                render=render,
                renderer_url=RENDERER_URL,
                use_model_provider=use_model_provider,
                model_provider_name=model_provider,
            )
        )
        result = pipeline.run(source=source, job_id=job_id, transcript=transcript)
        jobs[job_id]["status"] = result.status
        jobs[job_id]["result"] = result.model_dump(mode="json")
    except Exception as exc:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(exc)


def _resolve_allowed_transcript_path(value: str) -> Path:
    raw_path = Path(value).expanduser()
    path = raw_path if raw_path.is_absolute() else Path.cwd() / raw_path
    resolved = path.resolve()
    allowed_roots = [(Path.cwd() / "fixtures").resolve(), UPLOAD_ROOT.resolve()]
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise HTTPException(
            status_code=400,
            detail="transcript_json_path must point inside fixtures/ or uploads/.",
        )
    return resolved


def _resolve_job_output_dir(job_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", job_id):
        raise HTTPException(status_code=400, detail="Invalid job id.")
    output_root = OUTPUT_ROOT.resolve()
    resolved = (output_root / job_id).resolve()
    if output_root != resolved and output_root not in resolved.parents:
        raise HTTPException(status_code=400, detail="Invalid job id.")
    return resolved
