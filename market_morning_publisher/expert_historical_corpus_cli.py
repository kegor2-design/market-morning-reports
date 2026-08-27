from __future__ import annotations

from pathlib import Path
import argparse
import json

from .expert_historical_corpus import (
    load_config, discover_expert_subtitles, build_inventory, write_inventory, load_inventory,
    prepare_batch, read_claim_ledger, build_primitive_index, build_validation_queue,
)


def _json_print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description="MarketMorningPublisher historical expert corpus helper")
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--config", default="config/expert_historical_corpus.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_inv = sub.add_parser("inventory")
    p_inv.add_argument("--expert", required=True)
    p_inv.add_argument("--source-root")
    p_inv.add_argument("--output-dir")
    p_inv.add_argument("--require-known-coverage", action="store_true")

    p_batch = sub.add_parser("next-batch")
    p_batch.add_argument("--inventory", required=True)
    p_batch.add_argument("--processed", required=True)
    p_batch.add_argument("--batch-size", type=int, default=8)
    p_batch.add_argument("--output", required=True)

    p_final = sub.add_parser("finalize")
    p_final.add_argument("--claims", required=True)
    p_final.add_argument("--output-dir", required=True)

    args = ap.parse_args()
    project = Path(args.project_root).resolve()
    config = Path(args.config)
    if not config.is_absolute():
        config = project / config
    cfg, experts = load_config(config)

    if args.cmd == "inventory":
        expert = experts[args.expert]
        files = discover_expert_subtitles(project, config, args.expert, args.source_root)
        items = build_inventory(args.expert, files)
        output_dir = Path(args.output_dir) if args.output_dir else project / cfg.get("storage_root", "data/state/expert_corpus") / args.expert
        summary = write_inventory(output_dir, expert, items)
        _json_print(summary)
        if args.require_known_coverage and not summary["coverage_pass"]:
            return 3
        return 0

    if args.cmd == "next-batch":
        inv = load_inventory(args.inventory)
        processed_path = Path(args.processed)
        processed = set(processed_path.read_text(encoding="utf-8").split()) if processed_path.exists() else set()
        batch = prepare_batch(inv.values(), processed, args.batch_size)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps({"videos": batch}, ensure_ascii=False, indent=2), encoding="utf-8")
        _json_print({"pending_batch": len(batch), "output": str(args.output)})
        return 0

    if args.cmd == "finalize":
        claims = read_claim_ledger(args.claims)
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        primitives = build_primitive_index(claims)
        (out / "primitive_index.json").write_text(json.dumps(primitives, ensure_ascii=False, indent=2), encoding="utf-8")
        queue = build_validation_queue(claims)
        (out / "validation_queue.json").write_text(json.dumps({"validation_tasks": queue}, ensure_ascii=False, indent=2), encoding="utf-8")
        _json_print({"claims": len(claims), "primitives": len(primitives["primitives"]), "validation_tasks": len(queue)})
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
