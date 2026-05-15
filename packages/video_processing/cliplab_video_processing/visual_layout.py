from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


LayoutMode = Literal[
    "single_speaker",
    "two_person_split_screen",
    "multi_speaker_wide",
    "screen_share_or_slides",
    "unknown",
]


@dataclass(frozen=True)
class FaceBox:
    sample_index: int
    timestamp: float
    source_timestamp: float | None
    x: int
    y: int
    width: int
    height: int
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "sample_index": self.sample_index,
            "timestamp": round(self.timestamp, 3),
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }
        if self.source_timestamp is not None:
            payload["source_timestamp"] = round(self.source_timestamp, 3)
        if self.confidence is not None:
            payload["confidence"] = round(self.confidence, 4)
        return payload


@dataclass(frozen=True)
class VisualSample:
    sample_index: int
    timestamp: float
    source_timestamp: float | None
    path: Path | None
    width: int
    height: int

    def to_dict(self, relative_to: Path | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "sample_index": self.sample_index,
            "timestamp": round(self.timestamp, 3),
            "width": self.width,
            "height": self.height,
        }
        if self.source_timestamp is not None:
            payload["source_timestamp"] = round(self.source_timestamp, 3)
        if self.path is not None:
            payload["path"] = _path_value(self.path, relative_to)
        return payload


@dataclass(frozen=True)
class LayoutAnalysis:
    layout_mode: LayoutMode
    layout_confidence: float
    face_boxes: list[FaceBox] = field(default_factory=list)
    visual_samples: list[VisualSample] = field(default_factory=list)
    reason: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_debug_dict(self, relative_to: Path | None = None) -> dict[str, Any]:
        return {
            "sampled_frame_timestamps": [
                sample.to_dict(relative_to=relative_to) for sample in self.visual_samples
            ],
            "detected_layout": self.layout_mode,
            "layout_confidence": round(self.layout_confidence, 4),
            "face_boxes": [face.to_dict() for face in self.face_boxes],
            "reason": self.reason,
            "metrics": self.metrics,
        }


def analyze_visual_layout(
    video_path: Path,
    debug_dir: Path,
    *,
    clip_start: float | None = None,
    clip_end: float | None = None,
) -> LayoutAnalysis:
    """Sample clip frames and classify the visual layout using lightweight CV heuristics."""
    debug_dir.mkdir(parents=True, exist_ok=True)
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except ImportError as exc:
        return LayoutAnalysis(
            layout_mode="unknown",
            layout_confidence=0.0,
            reason=f"OpenCV unavailable; skipped frame layout detection: {exc}",
        )

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return LayoutAnalysis(
            layout_mode="unknown",
            layout_confidence=0.0,
            reason=f"OpenCV could not open clip for visual layout detection: {video_path}",
        )

    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        frame_count = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        detected_duration = frame_count / fps if fps > 0 and frame_count > 0 else 0
        requested_duration = (clip_end - clip_start) if clip_start is not None and clip_end else 0
        duration = max(0.0, detected_duration or requested_duration)
        timestamps = _sample_timestamps(duration)
        face_cascade = _load_face_cascade(cv2)
        samples: list[VisualSample] = []
        face_boxes: list[FaceBox] = []
        frame_metrics: list[dict[str, Any]] = []

        for sample_index, timestamp in enumerate(timestamps, start=1):
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, timestamp) * 1000)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            height, width = frame.shape[:2]
            source_timestamp = clip_start + timestamp if clip_start is not None else None
            faces = _detect_faces(cv2, frame, face_cascade)
            sample_faces = [
                FaceBox(
                    sample_index=sample_index,
                    timestamp=timestamp,
                    source_timestamp=source_timestamp,
                    x=int(x),
                    y=int(y),
                    width=int(w),
                    height=int(h),
                )
                for x, y, w, h in faces
            ]
            face_boxes.extend(sample_faces)
            metrics = _measure_frame(cv2, np, frame, sample_index, sample_faces)
            frame_metrics.append(metrics)

            sample_path = debug_dir / f"sample_{sample_index:02d}_t{timestamp:07.3f}.jpg"
            _write_debug_frame(cv2, frame, sample_path, sample_faces)
            samples.append(
                VisualSample(
                    sample_index=sample_index,
                    timestamp=timestamp,
                    source_timestamp=source_timestamp,
                    path=sample_path,
                    width=width,
                    height=height,
                )
            )

        if not samples:
            return LayoutAnalysis(
                layout_mode="unknown",
                layout_confidence=0.0,
                reason="No frames could be sampled for visual layout detection.",
            )

        layout_mode, confidence, reason, aggregate_metrics = _classify_layout(frame_metrics)
        aggregate_metrics["samples"] = frame_metrics
        return LayoutAnalysis(
            layout_mode=layout_mode,
            layout_confidence=confidence,
            face_boxes=face_boxes,
            visual_samples=samples,
            reason=reason,
            metrics=aggregate_metrics,
        )
    finally:
        cap.release()


def _sample_timestamps(duration: float) -> list[float]:
    if duration <= 0:
        return [0.0]
    return [
        _clamp(1.0, 0.0, duration),
        _clamp(duration / 2, 0.0, duration),
        _clamp(duration - 1.0, 0.0, duration),
    ]


def _load_face_cascade(cv2: Any) -> Any | None:
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    if not cascade_path.exists():
        return None
    cascade = cv2.CascadeClassifier(str(cascade_path))
    if cascade.empty():
        return None
    return cascade


def _detect_faces(cv2: Any, frame: Any, face_cascade: Any | None) -> list[tuple[int, int, int, int]]:
    if face_cascade is None:
        return []
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    min_size = max(40, min(width, height) // 14)
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.08,
        minNeighbors=4,
        minSize=(min_size, min_size),
    )
    return _dedupe_faces([(int(x), int(y), int(w), int(h)) for x, y, w, h in faces])


def _dedupe_faces(faces: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    kept: list[tuple[int, int, int, int]] = []
    for face in sorted(faces, key=lambda box: box[2] * box[3], reverse=True):
        if all(_iou(face, existing) < 0.4 for existing in kept):
            kept.append(face)
    return sorted(kept, key=lambda box: box[0])


def _measure_frame(
    cv2: Any,
    np: Any,
    frame: Any,
    sample_index: int,
    faces: list[FaceBox],
) -> dict[str, Any]:
    height, width = frame.shape[:2]
    center_x = width // 2
    band = max(2, width // 200)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    sobel_x = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    center_band = sobel_x[:, center_x - band : center_x + band + 1]
    center_ratio = float(center_band.mean() / (sobel_x.mean() + 1e-6))
    vertical_split_score = _clamp((center_ratio - 1.3) / 2.5, 0.0, 1.0)

    edges = cv2.Canny(gray, 80, 160)
    margin = max(1, width // 20)
    left_edges = edges[:, margin : max(margin + 1, center_x - band)]
    right_edges = edges[:, min(width - margin, center_x + band) : width - margin]
    left_edge_density = float((left_edges > 0).mean()) if left_edges.size else 0.0
    right_edge_density = float((right_edges > 0).mean()) if right_edges.size else 0.0
    edge_balance = min(left_edge_density, right_edge_density) / (
        max(left_edge_density, right_edge_density) + 1e-6
    )

    left_mean = frame[:, : max(1, center_x - band)].mean(axis=(0, 1))
    right_mean = frame[:, min(width - 1, center_x + band) :].mean(axis=(0, 1))
    left_right_difference = float(np.mean(np.abs(left_mean - right_mean)) / 255)

    left_faces = _count_large_faces(faces, width, "left")
    right_faces = _count_large_faces(faces, width, "right")
    center_faces = _count_large_faces(faces, width, "center")

    return {
        "sample_index": sample_index,
        "width": width,
        "height": height,
        "aspect_ratio": round(width / height, 4) if height else 0,
        "vertical_split_score": round(vertical_split_score, 4),
        "center_edge_ratio": round(center_ratio, 4),
        "left_edge_density": round(left_edge_density, 5),
        "right_edge_density": round(right_edge_density, 5),
        "edge_balance": round(edge_balance, 4),
        "left_right_difference": round(left_right_difference, 4),
        "face_count": len(faces),
        "left_faces": left_faces,
        "right_faces": right_faces,
        "center_faces": center_faces,
    }


def _classify_layout(metrics: list[dict[str, Any]]) -> tuple[LayoutMode, float, str, dict[str, Any]]:
    sample_count = max(1, len(metrics))
    aspect_ratio = sum(item["aspect_ratio"] for item in metrics) / sample_count
    split_score = sum(item["vertical_split_score"] for item in metrics) / sample_count
    edge_balance = sum(item["edge_balance"] for item in metrics) / sample_count
    left_right_difference = sum(item["left_right_difference"] for item in metrics) / sample_count
    edge_density = sum(
        min(item["left_edge_density"], item["right_edge_density"]) for item in metrics
    ) / sample_count
    both_face_frames = sum(
        1 for item in metrics if item["left_faces"] >= 1 and item["right_faces"] >= 1
    )
    split_frames = sum(
        1
        for item in metrics
        if item["vertical_split_score"] >= 0.5
        and item["edge_balance"] >= 0.45
        and item["left_right_difference"] >= 0.06
    )
    face_counts = [item["face_count"] for item in metrics]
    max_faces = max(face_counts) if face_counts else 0
    one_sided_face_frames = sum(
        1
        for item in metrics
        if (item["left_faces"] >= 1) != (item["right_faces"] >= 1)
        or item["center_faces"] >= 1
    )

    aggregate = {
        "aspect_ratio": round(aspect_ratio, 4),
        "avg_vertical_split_score": round(split_score, 4),
        "avg_edge_balance": round(edge_balance, 4),
        "avg_left_right_difference": round(left_right_difference, 4),
        "avg_min_edge_density": round(edge_density, 5),
        "both_face_frame_ratio": round(both_face_frames / sample_count, 4),
        "split_frame_ratio": round(split_frames / sample_count, 4),
        "max_face_count": max_faces,
    }

    if aspect_ratio >= 1.3 and both_face_frames > 0:
        confidence = _clamp(
            0.72
            + 0.16 * (both_face_frames / sample_count)
            + 0.08 * split_score
            + 0.04 * edge_balance,
            0.0,
            0.98,
        )
        return (
            "two_person_split_screen",
            confidence,
            "Large face regions were detected on both left and right halves of a wide frame.",
            aggregate,
        )

    if aspect_ratio >= 1.3 and split_frames / sample_count >= 0.67:
        confidence = _clamp(0.55 + 0.25 * split_score + 0.1 * edge_balance, 0.0, 0.9)
        return (
            "two_person_split_screen",
            confidence,
            "Wide frame has a strong center split plus balanced visual activity on both sides.",
            aggregate,
        )

    if aspect_ratio >= 1.3 and max_faces >= 3:
        return (
            "multi_speaker_wide",
            0.68,
            "Multiple face regions were detected in a wide frame.",
            aggregate,
        )

    if max_faces >= 1 and one_sided_face_frames / sample_count >= 0.5:
        return (
            "single_speaker",
            _clamp(0.58 + 0.18 * (one_sided_face_frames / sample_count), 0.0, 0.86),
            "Face regions are concentrated on one side or near center without a split-screen seam.",
            aggregate,
        )

    if max_faces == 0 and edge_density >= 0.05 and aspect_ratio >= 1.2:
        return (
            "screen_share_or_slides",
            0.54,
            "No faces detected, but the frame has dense rectangular edge activity.",
            aggregate,
        )

    return (
        "unknown",
        0.25,
        "No confident single-speaker, split-screen, wide multi-speaker, or slide layout signal.",
        aggregate,
    )


def _write_debug_frame(cv2: Any, frame: Any, output_path: Path, faces: list[FaceBox]) -> None:
    annotated = frame.copy()
    height, width = annotated.shape[:2]
    cv2.line(annotated, (width // 2, 0), (width // 2, height), (0, 255, 255), 3)
    for face in faces:
        cv2.rectangle(
            annotated,
            (face.x, face.y),
            (face.x + face.width, face.y + face.height),
            (0, 255, 0),
            3,
        )
    cv2.imwrite(str(output_path), annotated)


def _count_large_faces(faces: list[FaceBox], frame_width: int, side: str) -> int:
    count = 0
    for face in faces:
        center_x = face.x + face.width / 2
        relative_area = (face.width * face.height) / max(1, frame_width * frame_width)
        if relative_area < 0.004:
            continue
        if side == "left" and center_x < frame_width * 0.46:
            count += 1
        elif side == "right" and center_x > frame_width * 0.54:
            count += 1
        elif side == "center" and frame_width * 0.42 <= center_x <= frame_width * 0.58:
            count += 1
    return count


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    inter_w = max(0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0, min(ay2, by2) - max(ay1, by1))
    intersection = inter_w * inter_h
    union = aw * ah + bw * bh - intersection
    return intersection / union if union else 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _path_value(path: Path, relative_to: Path | None) -> str:
    if relative_to is not None:
        try:
            return path.relative_to(relative_to).as_posix()
        except ValueError:
            pass
    return str(path)
