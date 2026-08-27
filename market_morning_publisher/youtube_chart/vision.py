from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


_PRICE_RE = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")
_TIMEFRAME_RE = re.compile(r"(?:^|\b)(1|2|3|5|10|15|30|45|60|120|240)\s*(m|min|분|h|hr|시간)(?:봉)?(?:\b|$)|(?:^|\b)(D|W|M|일봉|주봉|월봉)(?:\b|$)", re.I)
_TIME_AXIS_RE = re.compile(
    r"(?:\d{1,2}:\d{2})|(?:\d{4}[-./]\d{1,2}(?:[-./]\d{1,2})?)|"
    r"(?:\d{1,2}[-./]\d{1,2})|(?:\d{1,2}월(?:\s*\d{1,2}일)?)|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}", re.I,
)
_INDICATORS = {
    "VWAP": ("vwap", "avwap", "anchored vwap", "거래량가중평균"),
    "MOVING_AVERAGE": ("sma", "ema", "moving average", "이동평균", "이평선", "이평"),
    "SUPPORT": ("support", "지지선", "지지"),
    "RESISTANCE": ("resistance", "저항선", "저항"),
}


@dataclass(frozen=True)
class OcrToken:
    text: str
    confidence: float
    polygon: tuple[tuple[float, float], ...]

    @property
    def center(self) -> tuple[float, float]:
        return (
            sum(point[0] for point in self.polygon) / len(self.polygon),
            sum(point[1] for point in self.polygon) / len(self.polygon),
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["polygon"] = [list(point) for point in self.polygon]
        return value


def _token(text: Any, score: Any, polygon: Any) -> OcrToken | None:
    try:
        points = tuple((float(point[0]), float(point[1])) for point in polygon)
        confidence = float(score)
    except (TypeError, ValueError, IndexError):
        return None
    cleaned = str(text).strip()
    if not cleaned or len(points) < 2 or not math.isfinite(confidence):
        return None
    return OcrToken(cleaned, confidence, points)


def parse_paddle_result(result: Any) -> list[OcrToken]:
    """Normalize common PaddleOCR 2.x and 3.x result shapes."""
    tokens: list[OcrToken] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            wrapped = node.get("res") if isinstance(node.get("res"), dict) else node
            texts = wrapped.get("rec_texts")
            scores = wrapped.get("rec_scores")
            polygons = wrapped.get("rec_polys")
            if polygons is None:
                polygons = wrapped.get("dt_polys")
            is_indexable = lambda value: not isinstance(value, (str, bytes)) and hasattr(value, "__len__") and hasattr(value, "__getitem__")
            if is_indexable(texts) and is_indexable(scores) and is_indexable(polygons):
                for text, score, polygon in zip(texts, scores, polygons):
                    parsed = _token(text, score, polygon)
                    if parsed:
                        tokens.append(parsed)
                return
            for value in node.values():
                visit(value)
            return
        if isinstance(node, (list, tuple)):
            if len(node) == 2 and isinstance(node[1], (list, tuple)) and len(node[1]) == 2:
                parsed = _token(node[1][0], node[1][1], node[0])
                if parsed:
                    tokens.append(parsed)
                    return
            for value in node:
                visit(value)

    visit(result)
    return tokens


class PaddleOcrEngine:
    def __init__(self, *, languages: tuple[str, ...] = ("korean", "en")) -> None:
        self.languages = languages
        self._engines: list[Any] | None = None

    def _load(self) -> list[Any]:
        if self._engines is None:
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:
                raise RuntimeError("PaddleOCR is optional; install requirements-youtube-chart.txt") from exc
            self._engines = [
                PaddleOCR(
                    text_detection_model_name="PP-OCRv5_mobile_det",
                    text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
                    device="cpu",
                    enable_mkldnn=False,
                    cpu_threads=1,
                    text_recognition_batch_size=1,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    text_det_limit_side_len=1280,
                    text_det_limit_type="max",
                )
            ]
        return self._engines

    def recognize(self, image_path: Path) -> list[OcrToken]:
        tokens: list[OcrToken] = []
        seen: set[tuple[str, int, int]] = set()
        for engine in self._load():
            result = engine.predict(str(image_path)) if hasattr(engine, "predict") else engine.ocr(str(image_path), cls=False)
            for item in parse_paddle_result(result):
                x, y = item.center
                key = (item.text.lower(), round(x / 4), round(y / 4))
                if key not in seen:
                    tokens.append(item)
                    seen.add(key)
        return tokens


def price_at_pixel(axis_fit: dict[str, Any], pixel_y: float) -> float | None:
    if axis_fit.get("status") != "FITTED":
        return None
    transformed = float(axis_fit["intercept"]) + float(axis_fit["slope"]) * pixel_y
    value = math.exp(transformed) if axis_fit.get("scale") == "LOG" else transformed
    return value if math.isfinite(value) and value > 0 else None


def normalize_timeframe_label(value: str) -> str | None:
    lowered = re.sub(r"\s+", "", value.lower())
    minute_map = {
        "1": "MINUTE_1", "5": "MINUTE_5", "15": "MINUTE_15", "30": "MINUTE_30",
        "60": "HOUR_1",
    }
    match = re.search(r"(1|5|15|30|60)(?:m|min|분)", lowered)
    if match:
        return minute_map[match.group(1)]
    if "1시간" in lowered or "hourly" in lowered or "1hour" in lowered:
        return "HOUR_1"
    if "일봉" in lowered or "daily" in lowered or lowered == "d":
        return "DAILY"
    if "주봉" in lowered or "weekly" in lowered or lowered == "w":
        return "WEEKLY"
    if "월봉" in lowered or "monthly" in lowered or lowered == "m":
        return "MONTHLY"
    return None


def recognize_overlays(
    tokens: Iterable[OcrToken], line_candidates: Iterable[dict[str, Any]] = (),
    *, axis_fit: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    overlays: list[dict[str, Any]] = []
    for token in tokens:
        lowered = token.text.lower()
        for kind, aliases in _INDICATORS.items():
            if any(alias in lowered for alias in aliases):
                overlay = {
                    "kind": kind, "evidence": "OCR_LABEL", "label": token.text,
                    "confidence": round(token.confidence, 4), "semantic_status": "EXPLICIT",
                    "pixel_y": round(token.center[1], 3),
                }
                overlays.append(overlay)
                break
    for line in line_candidates:
        if line.get("orientation") == "HORIZONTAL":
            pixel_y = (float(line.get("y1", 0)) + float(line.get("y2", 0))) / 2
            estimated = price_at_pixel(axis_fit or {}, pixel_y)
            overlay = {
                "kind": "HORIZONTAL_LEVEL", "evidence": "CV_GEOMETRY", "geometry": line,
                "confidence": line.get("confidence"), "semantic_status": "REVIEW_REQUIRED",
            }
            if estimated is not None:
                overlay["estimated_price"] = round(estimated, 8)
            overlays.append(overlay)
    return overlays


def extract_screen_fields(tokens: Iterable[OcrToken], *, width: int, height: int, assets: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    values = list(tokens)
    price_axis = []
    timeframe = []
    time_axis = []
    for token in values:
        x, y = token.center
        if x >= width * 0.72 and _PRICE_RE.match(token.text.replace(" ", "")):
            raw = token.text.replace(" ", "")
            try:
                price_axis.append({"text": raw, "value": float(raw.replace(",", "")), "pixel_y": round(y, 3), "confidence": token.confidence})
            except ValueError:
                pass
        if _TIMEFRAME_RE.search(token.text):
            timeframe.append({
                "text": token.text, "normalized": normalize_timeframe_label(token.text),
                "confidence": token.confidence, "pixel_x": round(x, 3), "pixel_y": round(y, 3),
            })
        if y >= height * 0.78 and _TIME_AXIS_RE.search(token.text):
            time_axis.append({"text": token.text, "confidence": token.confidence, "pixel_x": round(x, 3), "pixel_y": round(y, 3)})
    full_text = " ".join(token.text for token in values).lower()
    asset_matches = []
    for asset in assets:
        candidates = [str(asset.get("symbol", "")), str(asset.get("name", "")), *asset.get("aliases", [])]
        if any(candidate and candidate.lower() in full_text for candidate in candidates):
            asset_matches.append({"symbol": asset.get("symbol"), "name": asset.get("name")})
    return {
        "price_axis_ticks": price_axis, "time_axis_labels": time_axis,
        "timeframe_candidates": timeframe, "asset_candidates": asset_matches,
    }


def _fit(points: list[tuple[float, float]], *, logarithmic: bool) -> dict[str, Any] | None:
    if logarithmic and any(price <= 0 for _, price in points):
        return None
    xs = [y for y, _ in points]
    ys = [math.log(price) if logarithmic else price for _, price in points]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    denominator = sum((value - mean_x) ** 2 for value in xs)
    if denominator == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
    intercept = mean_y - slope * mean_x
    predicted = [intercept + slope * x for x in xs]
    total = sum((value - mean_y) ** 2 for value in ys)
    residual = sum((value - guess) ** 2 for value, guess in zip(ys, predicted))
    r_squared = 1.0 - residual / total if total else 1.0
    return {"slope": slope, "intercept": intercept, "r_squared": r_squared, "scale": "LOG" if logarithmic else "LINEAR"}


def fit_price_axis(ticks: Iterable[dict[str, Any]], *, min_confidence: float = 0.55) -> dict[str, Any]:
    points = [(float(tick["pixel_y"]), float(tick["value"])) for tick in ticks if float(tick.get("confidence", 0)) >= min_confidence]
    unique = list(dict.fromkeys(points))
    if len(unique) < 2:
        return {"status": "UNKNOWN", "reason": "FEWER_THAN_TWO_RELIABLE_TICKS"}
    candidates = [
        candidate
        for candidate in (
            _fit(unique, logarithmic=False),
            _fit(unique, logarithmic=True),
        )
        if candidate
    ]

    if not candidates:
        return {
            "status": "UNKNOWN",
            "reason": "AXIS_FIT_DEGENERATE",
            "tick_count": len(unique),
        }

    best = max(candidates, key=lambda item: item["r_squared"])
    if best["r_squared"] < 0.9:
        return {"status": "UNKNOWN", "reason": "AXIS_FIT_LOW_CONFIDENCE", "r_squared": round(best["r_squared"], 6)}
    return {"status": "FITTED", **{key: round(value, 10) if isinstance(value, float) else value for key, value in best.items()}, "tick_count": len(unique)}


def detect_line_candidates(image_path: Path, *, min_length_ratio: float = 0.18) -> list[dict[str, Any]]:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is optional; install requirements-youtube-chart.txt") from exc
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"cannot read image: {image_path}")
    height, width = image.shape[:2]
    edges = cv2.Canny(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 60, 160)
    raw = cv2.HoughLinesP(edges, 1, math.pi / 180, threshold=70, minLineLength=int(width * min_length_ratio), maxLineGap=12)
    result = []
    if raw is None:
        return result
    for row in raw:
        x1, y1, x2, y2 = (int(value) for value in row[0])
        dx, dy = x2 - x1, y2 - y1
        angle = abs(math.degrees(math.atan2(dy, dx)))
        orientation = "HORIZONTAL" if angle <= 3 or angle >= 177 else "OTHER"
        if orientation == "HORIZONTAL":
            result.append({
                "x1": x1, "y1": y1, "x2": x2, "y2": y2, "orientation": orientation,
                "length_ratio": round(math.hypot(dx, dy) / width, 4),
                "confidence": round(min(0.99, math.hypot(dx, dy) / width), 4),
            })
    deduplicated = []
    for candidate in sorted(result, key=lambda item: item["confidence"], reverse=True):
        center_y = (candidate["y1"] + candidate["y2"]) / 2
        if any(abs(center_y - (kept["y1"] + kept["y2"]) / 2) <= 3 for kept in deduplicated):
            continue
        deduplicated.append(candidate)
        if len(deduplicated) >= 100:
            break
    return deduplicated
