from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import json
import math

UTC = timezone.utc
CONTRACT = "MMP_MI_PREDICTION_SCOREBOARD_V1"
PREDICTION_CONTRACT = "MMP_MI_PREDICTION_V1"
EVALUATION_CONTRACT = "MMP_MI_PREDICTION_EVALUATION_V1"
DIRECTIONS = {"UP", "DOWN", "FLAT"}
EVAL_STATES = {"PENDING", "MATURED", "SCORED", "INCONCLUSIVE", "INVALIDATED"}


def _parse_dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(x or "") for x in parts)
    return f"{prefix}_{sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def horizon_delta(horizon: str) -> timedelta:
    table = {
        "INTRADAY": timedelta(hours=6),
        "1D": timedelta(days=1),
        "3D": timedelta(days=3),
        "1W": timedelta(days=7),
        "2W": timedelta(days=14),
        "1M": timedelta(days=30),
        "3M": timedelta(days=90),
        "6M": timedelta(days=180),
        "1Y": timedelta(days=365),
    }
    try:
        return table[horizon]
    except KeyError as exc:
        raise ValueError(f"unsupported horizon: {horizon}") from exc


@dataclass(frozen=True)
class PredictionRecord:
    prediction_id: str
    mi_id: str
    predictor_id: str
    created_at: str
    as_of: str
    target_asset: str
    target_metric: str
    horizon: str
    direction: str
    confidence: float
    baseline_value: float
    flat_band_pct: float = 0.25
    expected_range_low: float | None = None
    expected_range_high: float | None = None
    regime: str | None = None
    event_ids: tuple[str, ...] = ()
    primitive_keys: tuple[str, ...] = ()
    expert_claim_ids: tuple[str, ...] = ()
    source_registry_ids: tuple[str, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()
    rationale_snapshot: str = ""
    context_snapshot_sha256: str = ""
    status: str = "PENDING"
    contract: str = PREDICTION_CONTRACT

    def __post_init__(self) -> None:
        if not str(self.predictor_id).strip():
            raise ValueError("predictor_id is required")
        if self.direction not in DIRECTIONS:
            raise ValueError(f"invalid direction: {self.direction}")
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("confidence must be within [0,1]")
        if float(self.baseline_value) <= 0:
            raise ValueError("baseline_value must be positive")
        if float(self.flat_band_pct) < 0:
            raise ValueError("flat_band_pct must be >= 0")
        horizon_delta(self.horizon)
        if self.status not in EVAL_STATES:
            raise ValueError(f"invalid status: {self.status}")
        if _parse_dt(self.created_at) < _parse_dt(self.as_of):
            raise ValueError("created_at cannot precede as_of")

    @property
    def comparison_key(self) -> str:
        return _stable_id("cmp", self.as_of, self.target_asset, self.target_metric, self.horizon)

    @property
    def maturity_at(self) -> str:
        return _iso(_parse_dt(self.as_of) + horizon_delta(self.horizon))

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["maturity_at"] = self.maturity_at
        row["comparison_key"] = self.comparison_key
        return row

    @classmethod
    def create(
        cls,
        *,
        mi_id: str,
        as_of: str,
        predictor_id: str = "OUR_MI_ENGINE",
        target_asset: str,
        target_metric: str,
        horizon: str,
        direction: str,
        confidence: float,
        baseline_value: float,
        created_at: str | None = None,
        flat_band_pct: float = 0.25,
        expected_range_low: float | None = None,
        expected_range_high: float | None = None,
        regime: str | None = None,
        event_ids: Sequence[str] = (),
        primitive_keys: Sequence[str] = (),
        expert_claim_ids: Sequence[str] = (),
        source_registry_ids: Sequence[str] = (),
        invalidation_conditions: Sequence[str] = (),
        rationale_snapshot: str = "",
        context_snapshot: Mapping[str, Any] | None = None,
    ) -> "PredictionRecord":
        as_of_iso = _iso(_parse_dt(as_of))
        created_iso = _iso(_parse_dt(created_at or as_of_iso))
        context_raw = json.dumps(context_snapshot or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        context_sha = sha256(context_raw.encode("utf-8")).hexdigest()
        pid = _stable_id("pred", predictor_id, mi_id, as_of_iso, target_asset, target_metric, horizon, direction, baseline_value)
        return cls(
            prediction_id=pid,
            mi_id=str(mi_id),
            predictor_id=str(predictor_id or "OUR_MI_ENGINE"),
            created_at=created_iso,
            as_of=as_of_iso,
            target_asset=str(target_asset),
            target_metric=str(target_metric),
            horizon=str(horizon),
            direction=str(direction).upper(),
            confidence=float(confidence),
            baseline_value=float(baseline_value),
            flat_band_pct=float(flat_band_pct),
            expected_range_low=float(expected_range_low) if expected_range_low is not None else None,
            expected_range_high=float(expected_range_high) if expected_range_high is not None else None,
            regime=str(regime) if regime else None,
            event_ids=tuple(sorted({str(x) for x in event_ids if str(x)})),
            primitive_keys=tuple(sorted({str(x) for x in primitive_keys if str(x)})),
            expert_claim_ids=tuple(sorted({str(x) for x in expert_claim_ids if str(x)})),
            source_registry_ids=tuple(sorted({str(x) for x in source_registry_ids if str(x)})),
            invalidation_conditions=tuple(str(x) for x in invalidation_conditions if str(x)),
            rationale_snapshot=str(rationale_snapshot or ""),
            context_snapshot_sha256=context_sha,
        )

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PredictionRecord":
        fields = {k: v for k, v in dict(raw).items() if k in cls.__dataclass_fields__}
        fields.setdefault("predictor_id", "OUR_MI_ENGINE")
        for key in ("event_ids", "primitive_keys", "expert_claim_ids", "source_registry_ids", "invalidation_conditions"):
            fields[key] = tuple(fields.get(key) or ())
        return cls(**fields)


@dataclass(frozen=True)
class Observation:
    observed_at: str
    value: float

    def __post_init__(self) -> None:
        _parse_dt(self.observed_at)
        if not math.isfinite(float(self.value)):
            raise ValueError("observation value must be finite")


@dataclass(frozen=True)
class PredictionEvaluation:
    evaluation_id: str
    prediction_id: str
    mi_id: str
    evaluated_at: str
    state: str
    actual_direction: str | None
    terminal_value: float | None
    terminal_return_pct: float | None
    mfe_pct: float | None
    mae_pct: float | None
    direction_correct: bool | None
    range_hit: bool | None
    confidence: float
    score: float | None
    brier_loss: float | None
    reason: str
    causal_validation_status: str = "SEPARATE_NOT_SCORED_HERE"
    contract: str = EVALUATION_CONTRACT

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _classify_direction(ret: float, flat_band_pct: float) -> str:
    if ret > flat_band_pct:
        return "UP"
    if ret < -flat_band_pct:
        return "DOWN"
    return "FLAT"


def _correctness_score(predicted: str, actual: str, confidence: float) -> float:
    # confidence-weighted signed score, useful for ranking/calibration; accuracy remains separately visible.
    return float(confidence) if predicted == actual else -float(confidence)


def evaluate_prediction(
    prediction: PredictionRecord,
    observations: Iterable[Observation | Mapping[str, Any]],
    *,
    evaluated_at: str,
) -> PredictionEvaluation:
    now = _parse_dt(evaluated_at)
    as_of = _parse_dt(prediction.as_of)
    maturity = _parse_dt(prediction.maturity_at)
    if now < maturity:
        return PredictionEvaluation(
            _stable_id("eval", prediction.prediction_id, _iso(now)), prediction.prediction_id, prediction.mi_id,
            _iso(now), "PENDING", None, None, None, None, None, None, None,
            prediction.confidence, None, None, "horizon_not_matured"
        )

    clean: list[Observation] = []
    for raw in observations:
        obs = raw if isinstance(raw, Observation) else Observation(str(raw["observed_at"]), float(raw["value"]))
        ts = _parse_dt(obs.observed_at)
        # Strict point-in-time window: nothing before prediction as_of and nothing after evaluator's now.
        if as_of < ts <= now:
            clean.append(obs)
    clean.sort(key=lambda x: _parse_dt(x.observed_at))
    if not clean:
        return PredictionEvaluation(
            _stable_id("eval", prediction.prediction_id, _iso(now)), prediction.prediction_id, prediction.mi_id,
            _iso(now), "INCONCLUSIVE", None, None, None, None, None, None, None,
            prediction.confidence, None, None, "no_post_prediction_observations"
        )

    matured = [x for x in clean if _parse_dt(x.observed_at) >= maturity]
    if not matured:
        return PredictionEvaluation(
            _stable_id("eval", prediction.prediction_id, _iso(now)), prediction.prediction_id, prediction.mi_id,
            _iso(now), "INCONCLUSIVE", None, None, None, None, None, None, None,
            prediction.confidence, None, None, "no_observation_at_or_after_maturity"
        )

    terminal = matured[0]
    base = prediction.baseline_value
    terminal_ret = (float(terminal.value) / base - 1.0) * 100.0
    path_until_terminal = [x for x in clean if _parse_dt(x.observed_at) <= _parse_dt(terminal.observed_at)]
    returns = [(float(x.value) / base - 1.0) * 100.0 for x in path_until_terminal]
    mfe = max(returns) if returns else terminal_ret
    mae = min(returns) if returns else terminal_ret
    actual = _classify_direction(terminal_ret, prediction.flat_band_pct)
    correct = prediction.direction == actual
    range_hit = None
    if prediction.expected_range_low is not None or prediction.expected_range_high is not None:
        lo = prediction.expected_range_low if prediction.expected_range_low is not None else -math.inf
        hi = prediction.expected_range_high if prediction.expected_range_high is not None else math.inf
        range_hit = float(lo) <= float(terminal.value) <= float(hi)
    return PredictionEvaluation(
        evaluation_id=_stable_id("eval", prediction.prediction_id, terminal.observed_at),
        prediction_id=prediction.prediction_id,
        mi_id=prediction.mi_id,
        evaluated_at=_iso(now),
        state="SCORED",
        actual_direction=actual,
        terminal_value=float(terminal.value),
        terminal_return_pct=terminal_ret,
        mfe_pct=mfe,
        mae_pct=mae,
        direction_correct=correct,
        range_hit=range_hit,
        confidence=prediction.confidence,
        score=_correctness_score(prediction.direction, actual, prediction.confidence),
        brier_loss=(prediction.confidence - (1.0 if correct else 0.0)) ** 2,
        reason="matured_and_scored",
    )


def confidence_bucket(confidence: float, buckets: Sequence[Mapping[str, Any]] | None = None) -> str:
    buckets = buckets or (
        {"label": "LOW", "min": 0.0, "max": 0.60},
        {"label": "MEDIUM", "min": 0.60, "max": 0.75},
        {"label": "HIGH", "min": 0.75, "max": 1.01},
    )
    value = float(confidence)
    for row in buckets:
        if float(row["min"]) <= value < float(row["max"]):
            return str(row["label"])
    return "UNBUCKETED"


def _summary(rows: Sequence[tuple[PredictionRecord, PredictionEvaluation]], buckets: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    scored = [(p, e) for p, e in rows if e.state == "SCORED" and e.direction_correct is not None]
    if not scored:
        return {"count": 0, "accuracy": None, "mean_confidence": None, "calibration_gap": None, "mean_score": None, "mean_brier_loss": None}
    accuracy = sum(1 for _, e in scored if e.direction_correct) / len(scored)
    mean_conf = sum(float(p.confidence) for p, _ in scored) / len(scored)
    mean_score = sum(float(e.score or 0.0) for _, e in scored) / len(scored)
    mean_brier = sum(float(e.brier_loss or 0.0) for _, e in scored) / len(scored)
    return {
        "count": len(scored),
        "accuracy": accuracy,
        "mean_confidence": mean_conf,
        "calibration_gap": mean_conf - accuracy,
        "mean_score": mean_score,
        "mean_brier_loss": mean_brier,
    }


def build_scoreboard(
    predictions: Iterable[PredictionRecord],
    evaluations: Iterable[PredictionEvaluation],
    *,
    confidence_buckets: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    pred_map = {p.prediction_id: p for p in predictions}
    latest_eval: dict[str, PredictionEvaluation] = {}
    for e in evaluations:
        if e.prediction_id not in pred_map:
            continue
        prev = latest_eval.get(e.prediction_id)
        if prev is None or _parse_dt(e.evaluated_at) >= _parse_dt(prev.evaluated_at):
            latest_eval[e.prediction_id] = e
    pairs = [(pred_map[pid], e) for pid, e in latest_eval.items()]

    def grouped(keys_fn):
        groups: dict[str, list[tuple[PredictionRecord, PredictionEvaluation]]] = {}
        for p, e in pairs:
            for key in keys_fn(p):
                groups.setdefault(str(key), []).append((p, e))
        return {k: _summary(v, confidence_buckets) for k, v in sorted(groups.items())}

    scored_pairs = [(p, e) for p, e in pairs if e.state == "SCORED"]
    bucket_rows: dict[str, list[tuple[PredictionRecord, PredictionEvaluation]]] = {}
    for p, e in scored_pairs:
        bucket_rows.setdefault(confidence_bucket(p.confidence, confidence_buckets), []).append((p, e))

    comparison_groups: dict[str, list[tuple[PredictionRecord, PredictionEvaluation]]] = {}
    for p, e in scored_pairs:
        comparison_groups.setdefault(p.comparison_key, []).append((p, e))
    matched_groups = [rows for rows in comparison_groups.values() if len({p.predictor_id for p, _ in rows}) >= 2]
    matched_by_predictor: dict[str, list[tuple[PredictionRecord, PredictionEvaluation]]] = {}
    head_to_head: dict[str, dict[str, int]] = {}
    for rows in matched_groups:
        for p, e in rows:
            matched_by_predictor.setdefault(p.predictor_id, []).append((p, e))
        # Pairwise correctness wins. A tie includes both-correct and both-wrong.
        ordered = sorted(rows, key=lambda x: x[0].predictor_id)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                pa, ea = ordered[i]; pb, eb = ordered[j]
                key = f"{pa.predictor_id}__vs__{pb.predictor_id}"
                row = head_to_head.setdefault(key, {"a_wins": 0, "b_wins": 0, "ties": 0, "matched": 0})
                row["matched"] += 1
                if bool(ea.direction_correct) and not bool(eb.direction_correct):
                    row["a_wins"] += 1
                elif bool(eb.direction_correct) and not bool(ea.direction_correct):
                    row["b_wins"] += 1
                else:
                    row["ties"] += 1

    return {
        "contract": CONTRACT,
        "generated_at": _iso(datetime.now(UTC)),
        "overall": _summary(pairs, confidence_buckets),
        "pending_count": sum(1 for _, e in pairs if e.state == "PENDING"),
        "inconclusive_count": sum(1 for _, e in pairs if e.state == "INCONCLUSIVE"),
        "by_confidence": {k: _summary(v, confidence_buckets) for k, v in sorted(bucket_rows.items())},
        "matched_comparison_groups": len(matched_groups),
        "matched_by_predictor": {k: _summary(v, confidence_buckets) for k, v in sorted(matched_by_predictor.items())},
        "head_to_head": head_to_head,
        "by_predictor": grouped(lambda p: [p.predictor_id]),
        "by_asset": grouped(lambda p: [p.target_asset]),
        "by_horizon": grouped(lambda p: [p.horizon]),
        "by_regime": grouped(lambda p: [p.regime or "UNKNOWN"]),
        "by_primitive": grouped(lambda p: p.primitive_keys or ["NONE"]),
        "by_expert_claim": grouped(lambda p: p.expert_claim_ids or ["NONE"]),
        "by_event": grouped(lambda p: p.event_ids or ["NONE"]),
        "by_source": grouped(lambda p: p.source_registry_ids or ["NONE"]),
    }


def append_jsonl_once(path: str | Path, row: Mapping[str, Any], *, id_field: str) -> bool:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    row_id = str(row[id_field])
    if p.exists():
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    existing = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(existing.get(id_field) or "") == row_id:
                    return False
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")
    return True


def load_predictions(path: str | Path) -> list[PredictionRecord]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[PredictionRecord] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(PredictionRecord.from_dict(json.loads(line)))
    return out


def load_evaluations(path: str | Path) -> list[PredictionEvaluation]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[PredictionEvaluation] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        fields = {k: v for k, v in raw.items() if k in PredictionEvaluation.__dataclass_fields__}
        out.append(PredictionEvaluation(**fields))
    return out
