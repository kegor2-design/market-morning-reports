from __future__ import annotations

import argparse
import json
from pathlib import Path

from .mi_prediction_scoreboard import (
    Observation,
    PredictionRecord,
    append_jsonl_once,
    build_scoreboard,
    evaluate_prediction,
    load_evaluations,
    load_predictions,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="MI prediction scoreboard")
    sub = ap.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create")
    create.add_argument("--prediction-json", required=True)
    create.add_argument("--ledger", required=True)

    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--prediction-json", required=True)
    evaluate.add_argument("--observations-json", required=True)
    evaluate.add_argument("--evaluated-at", required=True)
    evaluate.add_argument("--ledger", required=True)

    report = sub.add_parser("report")
    report.add_argument("--predictions", required=True)
    report.add_argument("--evaluations", required=True)
    report.add_argument("--output", required=True)

    args = ap.parse_args()
    if args.cmd == "create":
        raw = json.loads(Path(args.prediction_json).read_text(encoding="utf-8"))
        rec = PredictionRecord.create(**raw)
        appended = append_jsonl_once(args.ledger, rec.to_dict(), id_field="prediction_id")
        print(json.dumps({"appended": appended, "prediction": rec.to_dict()}, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "evaluate":
        raw = json.loads(Path(args.prediction_json).read_text(encoding="utf-8"))
        rec = PredictionRecord.from_dict(raw)
        obs_raw = json.loads(Path(args.observations_json).read_text(encoding="utf-8"))
        observations = [Observation(str(x["observed_at"]), float(x["value"])) for x in obs_raw]
        result = evaluate_prediction(rec, observations, evaluated_at=args.evaluated_at)
        appended = append_jsonl_once(args.ledger, result.to_dict(), id_field="evaluation_id")
        print(json.dumps({"appended": appended, "evaluation": result.to_dict()}, ensure_ascii=False, indent=2))
        return 0

    predictions = load_predictions(args.predictions)
    evaluations = load_evaluations(args.evaluations)
    output = build_scoreboard(predictions, evaluations)
    p = Path(args.output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(p), "overall": output["overall"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
