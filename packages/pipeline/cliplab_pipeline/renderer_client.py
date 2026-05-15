from __future__ import annotations

import time
from pathlib import Path

import httpx

from cliplab_shared import RenderJobSpec


class RemotionRendererClient:
    def __init__(self, base_url: str = "http://localhost:3100", timeout_sec: int = 900) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec

    def ensure_available(self) -> None:
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=5)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(
                "Remotion renderer is unavailable. Start the renderer service or rerun with "
                f"`--no-render`. Checked: {self.base_url}/health. {exc}"
            ) from exc

    def render(
        self,
        job_id: str,
        clip_index: int,
        props: RenderJobSpec,
        output_relative_path: Path,
    ) -> Path:
        payload = {
            "jobId": job_id,
            "clipIndex": clip_index,
            "outputRelativePath": output_relative_path.as_posix(),
            "props": {
                "videoUrl": props.video_url,
                "durationInFrames": props.duration_in_frames,
                "fps": props.fps,
                "width": props.width,
                "height": props.height,
                "subtitles": props.subtitles.model_dump(mode="json") if props.subtitles else None,
                "hook": props.hook.model_dump(mode="json") if props.hook else None,
                "effects": props.effects.model_dump(mode="json") if props.effects else None,
            },
        }
        with httpx.Client(timeout=30) as client:
            try:
                response = client.post(f"{self.base_url}/render", json=payload)
                response.raise_for_status()
                render_id = response.json()["renderId"]
            except httpx.HTTPError as exc:
                raise RuntimeError(
                    "Remotion renderer rejected the render request. Check the renderer service "
                    f"at {self.base_url}. {exc}"
                ) from exc
            deadline = time.time() + self.timeout_sec
            while time.time() < deadline:
                try:
                    status_response = client.get(f"{self.base_url}/render/{render_id}")
                    status_response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise RuntimeError(
                        "Remotion renderer became unavailable while polling render status. "
                        f"Render id: {render_id}. {exc}"
                    ) from exc
                status = status_response.json()
                if status["status"] == "done":
                    return Path(status["outputUrl"])
                if status["status"] == "error":
                    raise RuntimeError(
                        status.get("error") or f"Remotion render failed for render id {render_id}"
                    )
                time.sleep(2)
        raise TimeoutError(f"Remotion render timed out after {self.timeout_sec}s")
